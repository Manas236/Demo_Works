"""
Phase 4 step 1.5 — the stable BOQ line identifier, and the guard re-keyed onto it.

Why this file exists
--------------------
The over-claim guard used to key on `item_no`. That looked reasonable and was
wrong, and the client's own 97-line Sify schedule is what proves it: item
numbers **restart per section** (item `4` exists in both A and B) and section A
carries item `17` **twice**, on a flexible sprinkler drop at Rs 1,800 and a
150 mm butterfly valve at Rs 14,572.50.

So 87 priced lines collapsed into 77 guard entries, and the guard broke in both
directions at once — it waved Rs 1,99,122.50 of over-claim through and refused
Rs 84,071.00 of legitimate claim. Those two figures are asserted below as named
constants, against the real seeded BOQ rather than a synthetic fixture, because
they are the whole reason the identifier was built.

The other half of the file is the **round trip**. `_clean_lines()` builds a
fresh dict from named keys by construction, so an id that is not explicitly
carried across is dropped and re-minted on the next save — which orphans every
claim against that BOQ with no error anywhere. That is the single way this
change breaks, so all four posted-id paths are tested, plus the end-to-end
property they exist to protect.
"""

import copy
import random

import pytest

import boq as BQ
import demo_data as DD
import ra
from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

SECTIONS = [{"code": "A", "title": "Sprinkler", "areas": []}]


def posted(item_no, **over):
    """One line as the editor posts it."""
    row = {"item_no": item_no, "section": "A", "description": f"Line {item_no}",
           "unit": "Mtrs", "total_qty": "10", "supply_rate": "100",
           "install_rate": "50"}
    row.update(over)
    return row


def clean(rows):
    lines, err, _idx = BQ._clean_lines(rows, SECTIONS)
    assert not err, err
    return lines


@pytest.fixture()
def store():
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    yield STORE
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


@pytest.fixture()
def seeded(store):
    """The real 97-line Sify BOQ, seeded exactly as the app seeds it."""
    STORE["_boq_seeded"] = False
    BQ.ensure_demo_boq()
    return DD.BOQ_META["id"]


# ═══════════════════════════════════════════════════════════════════════════
# THE IDENTIFIER ITSELF
# ═══════════════════════════════════════════════════════════════════════════

def test_a_line_id_is_opaque_and_not_built_from_any_displayed_field():
    """
    The key must not be derivable from anything the client's staff can edit.

    A key made of `item_no`, `section` or `description` re-attributes every
    claim against a line the moment somebody fixes a typo in it — which is the
    failure this identifier exists to prevent, reintroduced through the back
    door.
    """
    a = clean([posted("4.1", description="Original text")])[0]
    b = clean([posted("4.1", description="Original text")])[0]

    # Same visible content, different ids: nothing about the id is a function
    # of the content.
    assert a["line_id"] != b["line_id"]

    for field in ("4.1", "A", "Original text", "Mtrs"):
        assert field not in a["line_id"]


def test_line_ids_are_unique_within_one_boq():
    lines = clean([posted(str(i)) for i in range(1, 51)])
    ids = [li["line_id"] for li in lines]
    assert len(set(ids)) == len(ids) == 50


def test_a_malformed_line_id_is_never_echoed_back():
    """A browser that sent something this shape is not one we take an id from."""
    for junk in ("", "   ", "not-hex", "ZZZZZZZZZZZZ", "abc", "a" * 40,
                 "../../etc", "<script>", None, 12345, True, {"a": 1}):
        li = clean([posted("1", line_id=junk)])[0]
        assert BQ._LINE_ID_RE.match(li["line_id"])
        assert li["line_id"] != junk


# ═══════════════════════════════════════════════════════════════════════════
# THE ROUND TRIP — the four posted-id paths
# ═══════════════════════════════════════════════════════════════════════════

def test_a_posted_line_id_is_kept_verbatim():
    """Path 1: present, well-formed, unused. This is the one that matters."""
    lid = BQ._new_line_id()
    assert clean([posted("1", line_id=lid)])[0]["line_id"] == lid


def test_a_missing_line_id_is_minted():
    """Path 2: absent or empty means a new line."""
    row = posted("1")
    row.pop("line_id", None)
    minted = clean([row])[0]["line_id"]
    assert BQ._LINE_ID_RE.match(minted)

    assert BQ._LINE_ID_RE.match(clean([posted("1", line_id="")])[0]["line_id"])


def test_a_duplicated_line_id_keeps_the_first_and_mints_the_rest():
    """
    Path 3: a duplicate is a copy-pasted row, which is a legitimate action
    producing a genuinely new line — so it is resolved, never rejected.
    """
    lid = BQ._new_line_id()
    lines = clean([posted("1", line_id=lid),
                   posted("2", line_id=lid),
                   posted("3", line_id=lid)])

    assert lines[0]["line_id"] == lid           # first keeps it
    assert lines[1]["line_id"] != lid           # the copies get their own
    assert lines[2]["line_id"] != lid
    assert len({li["line_id"] for li in lines}) == 3

    # And it is a save, not a rejection.
    _lines, err, _idx = BQ._clean_lines(
        [posted("1", line_id=lid), posted("2", line_id=lid)], SECTIONS)
    assert err == ""


def test_a_malformed_line_id_is_minted_not_rejected():
    """Path 4: don't trust it, don't echo it, don't refuse the save."""
    lines, err, _idx = BQ._clean_lines([posted("1", line_id="nonsense!!")],
                                       SECTIONS)
    assert err == ""
    assert BQ._LINE_ID_RE.match(lines[0]["line_id"])


def test_specification_headers_carry_ids_too():
    """
    Nothing claims against a header, but a revision has to carry every
    surviving line forward and a uniform rule is one fewer thing to get wrong.
    """
    lines = clean([posted("4", is_header=True), posted("4.1")])
    assert all(BQ._LINE_ID_RE.match(li["line_id"]) for li in lines)
    assert lines[0]["line_id"] != lines[1]["line_id"]


# ── The property the round trip exists to protect ───────────────────────────

def test_editing_a_boq_does_not_orphan_its_ra_claims(seeded):
    """
    THE regression this whole step is for.

    If `_clean_lines()` ever stops carrying the posted id across, every save
    re-mints every id and every RA claim against that BOQ silently stops
    matching — no error, no warning, and a guard that now reads zero claimed
    against every line. This drives a real edit through the real round trip
    (record -> editor payload -> POST -> `_clean_lines()`) and asserts every
    claim still matches afterwards.
    """
    boq = STORE["boqs"][seeded]
    priced = [li for li in boq["line_items"]
              if not li["is_header"] and li["total_qty"] > 0][:20]
    assert len(priced) == 20

    # Claim 1 unit against each of them.
    claims = [ra.build_claim(li, 1.0, li["supply_rate"], 0.0,
                             li["supply_rate"]) for li in priced]
    STORE["ra_bills"]["r1"] = {
        "id": "r1", "ref": "SF/RA/26-27/0001", "fy": "26-27",
        "date": "2026-08-06", "boq_id": seeded, "boq_ref": boq["ref"],
        "boq_rev_no": 0, "ra_no": 1, "leg": "supply", "claims": claims,
    }

    before = ra.claimed_by_line(seeded)
    assert len(before) == 20
    assert all(v == 1.0 for v in before.values())
    # Every claim resolves against a line in the approved schedule.
    approved = ra.approved_by_line(seeded)
    assert all(k in approved for k in before)

    # ── The edit: reshape the record into the editor's payload, change one
    #    unrelated field, and put it back through the save path.
    payload = []
    for li in boq["line_items"]:
        payload.append({
            "line_id": li["line_id"], "item_no": li["item_no"],
            "parent_item_no": li["parent_item_no"], "section": li["section"],
            "is_header": li["is_header"], "description": li["description"],
            "remark": li["remark"], "unit": li["unit"],
            "area_qty": li["area_qty"], "total_qty": li["total_qty"],
            "supply_base_rate": li["supply_base_rate"],
            "supply_escalation_pct": li["supply_escalation_pct"],
            "supply_rate": li["supply_rate"], "supply_hsn": li["supply_hsn"],
            "supply_gst_rate": li["supply_gst_rate"],
            "install_base_rate": li["install_base_rate"],
            "install_escalation_pct": li["install_escalation_pct"],
            "install_rate": li["install_rate"],
            "install_sac": li["install_sac"],
            "install_gst_rate": li["install_gst_rate"],
        })
    payload[0]["remark"] = "site note added by the office"

    resaved, err, _idx = BQ._clean_lines(payload, boq["sections"])
    assert not err, err
    boq["line_items"] = resaved
    assert boq["line_items"][0]["remark"] == "site note added by the office"

    # The claims themselves are untouched — they carry their own ids — so the
    # question is whether the SCHEDULE still answers to them.
    assert ra.claimed_by_line(seeded) == before
    after_approved = ra.approved_by_line(seeded)
    assert all(k in after_approved for k in before), \
        "the edit re-minted line ids: every claim is now orphaned"

    # The sharp end of it. One unit is already claimed against each of these
    # lines, so claiming the full approved quantity must be REFUSED. If the
    # edit had orphaned the ids, a claim built from the edited line would carry
    # a brand-new id, the guard would see nothing claimed against it, and this
    # would sail through — silently, which is the whole danger.
    edited = {li["line_id"]: li for li in boq["line_items"]}
    for lid, _leg in before:
        li = edited[lid]
        claim = ra.build_claim(li, li["total_qty"], li["supply_rate"], 0.0,
                               li["supply_rate"])
        breaches = ra.overclaims(seeded, "supply", [claim])
        assert len(breaches) == 1, \
            f"line {li['item_no']} stopped counting its earlier claim"
        assert breaches[0]["previously"] == 1.0


def test_the_seeded_boq_survives_its_own_prefill_round_trip(seeded):
    """
    `_demo_form_payload()` is a real record -> editor -> POST path, so it is a
    real chance to drop the id. It must hand every line's id to the editor.
    """
    boot, _prefill = BQ._demo_form_payload()
    stored = {li["line_id"] for li in STORE["boqs"][seeded]["line_items"]}

    assert len(boot["lines"]) == 97
    assert {row["line_id"] for row in boot["lines"]} == stored


def test_the_editor_starts_a_new_line_with_a_blank_id():
    """
    The browser never invents an id — the server is the only authority on it,
    so a new line, a copied row and a hand-edited payload all take one path.
    """
    assert "line_id: ''" in BQ._BOQ_JS


# ═══════════════════════════════════════════════════════════════════════════
# ACCEPTANCE — the ten collisions in the client's real schedule
# ═══════════════════════════════════════════════════════════════════════════
#
# Measured against the seeded 97-line Sify BOQ with the guard keyed on
# `item_no`. Both figures are supply-leg, at each line's own supply rate.

OVERCLAIM_ONCE_PERMITTED = 199_122.50    # Rs, waved through by the collapse
CLAIM_ONCE_WRONGLY_BLOCKED = 84_071.00   # Rs, refused although approved


def _collision_exposure(lines, approved):
    """
    (waved_through, wrongly_blocked) in rupees, for a given guard table.

    `approved` is {(key, leg): qty}. Where a line's own approved quantity does
    not equal what the guard would allow for it, the difference is money —
    over-claim permitted if the guard allows more, legitimate claim refused if
    it allows less.
    """
    waved = blocked = 0.0
    for li in lines:
        allowed = approved.get((li["_k"], "supply"))
        if allowed is None:
            continue
        true_qty, rate = li["total_qty"], li["supply_rate"]
        if allowed > true_qty:
            waved += (allowed - true_qty) * rate
        elif allowed < true_qty:
            blocked += (true_qty - allowed) * rate
    return round(waved, 2), round(blocked, 2)


def test_item_no_keying_really_did_cost_these_two_figures(seeded):
    """
    A control, and the reason the next test's constants are not arbitrary.

    It reconstructs the OLD `item_no` key over the real seeded schedule and
    shows it produces exactly the two figures. Without this, the next test
    could pass against any numbers at all.
    """
    lines = [dict(li, _k=li["item_no"])
             for li in STORE["boqs"][seeded]["line_items"] if not li["is_header"]]

    old = {}
    for li in lines:                       # last write wins, as a dict does
        for leg in ra.LEGS:
            old[(li["_k"], leg)] = li["total_qty"]

    assert len({li["_k"] for li in lines}) == 77      # 87 lines, 77 item numbers
    assert _collision_exposure(lines, old) == (OVERCLAIM_ONCE_PERMITTED,
                                               CLAIM_ONCE_WRONGLY_BLOCKED)


def test_the_line_id_key_costs_nothing_on_the_clients_real_schedule(seeded):
    """Every one of the 87 priced lines guards at its own approved quantity."""
    lines = [dict(li, _k=li["line_id"])
             for li in STORE["boqs"][seeded]["line_items"] if not li["is_header"]]
    approved = ra.approved_by_line(seeded)

    assert len({li["_k"] for li in lines}) == 87      # no line lost
    assert len(approved) == 87 * len(ra.LEGS)
    assert _collision_exposure(lines, approved) == (0.0, 0.0)


def test_both_section_a_item_17s_guard_independently(seeded):
    """
    The sharpest case in the client's file: one item number, two items, rates
    eight times apart. Under the old key one of them vanished.
    """
    boq = STORE["boqs"][seeded]
    both = [li for li in boq["line_items"]
            if li["section"] == "A" and li["item_no"] == "17"]
    assert len(both) == 2

    drop = next(li for li in both if li["supply_rate"] == 1800.0)
    valve = next(li for li in both if li["supply_rate"] == 14572.5)
    assert drop["line_id"] != valve["line_id"]

    approved = ra.approved_by_line(seeded)
    assert approved[(drop["line_id"], "supply")] == 1.0
    assert approved[(valve["line_id"], "supply")] == 1.0

    # Claiming the valve does not consume the drop's quantity.
    STORE["ra_bills"]["r1"] = {
        "id": "r1", "boq_id": seeded, "ra_no": 1, "leg": "supply",
        "claims": [ra.build_claim(valve, 1.0, 14572.5, 0.0, 14572.5)],
    }
    claimed = ra.claimed_by_line(seeded)
    assert claimed[(valve["line_id"], "supply")] == 1.0
    assert (drop["line_id"], "supply") not in claimed

    # So a full claim on the drop still passes, and a second on the valve does not.
    assert ra.overclaims(seeded, "supply",
                         [ra.build_claim(drop, 1.0, 1800.0, 0.0, 1800.0)]) == []
    assert len(ra.overclaims(seeded, "supply",
                             [ra.build_claim(valve, 1.0, 14572.5, 1.0, 14572.5)])) == 1


@pytest.mark.parametrize("item_no,section,expected_qty", [
    ("5",  "A", 155.0),    # was guarded at 12.0 — Rs 58,630 wrongly blocked
    ("21", "A", 7.0),      # was guarded at 3.0  — Rs 18,486 wrongly blocked
    ("19", "A", 2.0),      # was guarded at 1.0  — Rs  6,955 wrongly blocked
])
def test_a_legitimate_claim_that_used_to_be_blocked_now_passes(
        seeded, item_no, section, expected_qty):
    boq = STORE["boqs"][seeded]
    li = next(x for x in boq["line_items"]
              if x["section"] == section and x["item_no"] == item_no
              and not x["is_header"])
    assert li["total_qty"] == expected_qty

    claim = ra.build_claim(li, expected_qty, li["supply_rate"], 0.0,
                           li["supply_rate"])
    assert ra.overclaims(seeded, "supply", [claim]) == []


@pytest.mark.parametrize("item_no,section", [
    ("23", "A"), ("20", "A"), ("22", "A"), ("6", "A"), ("9", "A"),
    ("17", "A"),
])
def test_an_overclaim_that_used_to_be_waved_through_is_now_caught(
        seeded, item_no, section):
    """
    Each of these lines was guarded against a larger line's quantity that
    happened to share its item number, so a claim well past its own approved
    figure passed. Claiming one unit over must now be refused.
    """
    boq = STORE["boqs"][seeded]
    li = next(x for x in boq["line_items"]
              if x["section"] == section and x["item_no"] == item_no
              and not x["is_header"])

    over = li["total_qty"] + 1.0
    claim = ra.build_claim(li, over, li["supply_rate"], 0.0, li["supply_rate"])
    breaches = ra.overclaims(seeded, "supply", [claim])

    assert len(breaches) == 1
    assert breaches[0]["reason"] == "overclaim"
    assert breaches[0]["approved"] == li["total_qty"]
    assert breaches[0]["over"] == pytest.approx(1.0)
    # The message still names the item number, because that is what is written
    # on the measurement sheet in the operator's hand.
    assert f"Item {item_no}" in ra.overclaim_message(breaches[0])


def test_shuffling_the_boq_line_order_changes_no_guard_verdict(seeded):
    """
    The property that proves the collapse is GONE rather than rearranged.

    Under the `item_no` key the surviving entry was whichever colliding line
    happened to be written last, so reordering the schedule — an edit that
    changes no quantity — silently moved the guard. Here every verdict must be
    invariant under any permutation.
    """
    boq = STORE["boqs"][seeded]
    original = boq["line_items"]
    priced = [li for li in original if not li["is_header"]]

    baseline = ra.approved_by_line(seeded)
    verdicts = {}
    for li in priced:
        claim = ra.build_claim(li, li["total_qty"], li["supply_rate"], 0.0,
                               li["supply_rate"])
        verdicts[li["line_id"]] = ra.overclaims(seeded, "supply", [claim]) == []
    assert all(verdicts.values())          # a full claim on every line passes

    rng = random.Random(20260806)
    for _ in range(5):
        shuffled = original[:]
        rng.shuffle(shuffled)
        boq["line_items"] = shuffled

        assert ra.approved_by_line(seeded) == baseline
        for li in priced:
            claim = ra.build_claim(li, li["total_qty"], li["supply_rate"], 0.0,
                                   li["supply_rate"])
            assert (ra.overclaims(seeded, "supply", [claim]) == []) \
                == verdicts[li["line_id"]]

    boq["line_items"] = original


# ═══════════════════════════════════════════════════════════════════════════
# THE SEED
# ═══════════════════════════════════════════════════════════════════════════

def test_every_seeded_line_carries_a_wellformed_unique_id():
    ids = [li["line_id"] for li in DD.BOQ_LINES]
    assert len(ids) == 97
    assert len(set(ids)) == 97
    assert all(BQ._LINE_ID_RE.match(i) for i in ids)


def test_the_seeds_ids_are_deterministic():
    """
    `demo_data.py` is byte-for-byte reproducible, so its ids are generated with
    uuid5 off a fixed namespace and the line's source coordinate rather than
    uuid4. A random id would rewrite all 97 lines on every regeneration and,
    far worse, a re-seeded demo BOQ would stop matching the claims raised
    against it.
    """
    import uuid
    NS = uuid.UUID("6f0f1b7e-2c31-4b3a-9a1e-5d4c0b7a9e10")
    SEC_ROWS = {"A": 5, "B": 29, "C": 96}

    counts = {}
    for li in DD.BOQ_LINES:
        s = li["section"]
        i = counts.get(s, 0)
        counts[s] = i + 1
        expected = uuid.uuid5(NS, f"boqline:{s}:{SEC_ROWS[s] + i}").hex[:12]
        assert li["line_id"] == expected


def test_seeding_carries_the_ids_onto_the_record(seeded):
    stored = [li["line_id"] for li in STORE["boqs"][seeded]["line_items"]]
    assert stored == [li["line_id"] for li in DD.BOQ_LINES]


# ═══════════════════════════════════════════════════════════════════════════
# THE BACKFILL
# ═══════════════════════════════════════════════════════════════════════════

def test_the_backfill_fills_only_blanks_and_is_idempotent(store):
    kept = BQ._new_line_id()
    STORE["boqs"]["b1"] = {"id": "b1", "line_items": [
        {"item_no": "1", "line_id": kept},     # already has one
        {"item_no": "2"},                      # missing
        {"item_no": "3", "line_id": ""},       # blank
        {"item_no": "4", "line_id": "junk"},   # malformed
    ]}

    first = BQ.backfill_line_ids(STORE)
    assert first == {"boqs": 1, "lines": 3, "claims_without_ids": 0}

    lines = STORE["boqs"]["b1"]["line_items"]
    assert lines[0]["line_id"] == kept          # never replaced
    assert all(BQ._LINE_ID_RE.match(li["line_id"]) for li in lines)
    assert len({li["line_id"] for li in lines}) == 4

    # Idempotent: a second run fills nothing and changes nothing.
    snapshot = [li["line_id"] for li in lines]
    assert BQ.backfill_line_ids(STORE) == {"boqs": 0, "lines": 0,
                                           "claims_without_ids": 0}
    assert [li["line_id"] for li in lines] == snapshot


def test_the_backfill_reminted_a_duplicate_within_one_record(store):
    dupe = BQ._new_line_id()
    STORE["boqs"]["b1"] = {"id": "b1", "line_items": [
        {"item_no": "1", "line_id": dupe},
        {"item_no": "2", "line_id": dupe},
    ]}
    assert BQ.backfill_line_ids(STORE)["lines"] == 1

    ids = [li["line_id"] for li in STORE["boqs"]["b1"]["line_items"]]
    assert ids[0] == dupe and ids[1] != dupe


def test_the_backfill_counts_claims_it_cannot_repair(store):
    """
    It will not guess a claim back onto a line, and says so instead.

    Matching an existing claim would have to go through `item_no`, which is
    ambiguous on exactly the lines that matter — a guess would attach a claim
    to the wrong item at the wrong rate, silently. There were zero RA bills in
    existence when this ran, so a non-zero count means somebody needs to look.
    """
    STORE["boqs"]["b1"] = {"id": "b1", "line_items": [{"item_no": "1"}]}
    STORE["ra_bills"]["r1"] = {"id": "r1", "boq_id": "b1", "ra_no": 1,
                               "leg": "supply", "claims": [
                                   {"item_no": "1", "qty": 5.0},
                                   {"item_no": "2", "qty": 3.0,
                                    "line_id": BQ._new_line_id()}]}

    assert BQ.backfill_line_ids(STORE)["claims_without_ids"] == 1


def test_a_claim_with_no_line_id_matches_nothing_rather_than_falling_back(store):
    """
    A fallback to `item_no` would resurrect the collapse on exactly the
    ambiguous lines, and would do it silently. Skipping is the honest answer.
    """
    STORE["boqs"]["b1"] = {"id": "b1", "supersedes": "", "rev_no": 0,
                           "line_items": [{"item_no": "1", "line_id": BQ._new_line_id(),
                                           "total_qty": 10.0, "is_header": False,
                                           "supply_rate": 100.0, "install_rate": 0.0}]}
    STORE["ra_bills"]["r1"] = {"id": "r1", "boq_id": "b1", "ra_no": 1,
                               "leg": "supply",
                               "claims": [{"item_no": "1", "qty": 5.0}]}

    assert ra.claimed_by_line("b1") == {}


# ═══════════════════════════════════════════════════════════════════════════
# REVISIONS
# ═══════════════════════════════════════════════════════════════════════════

def _rev_boq(bid, lines, rev_no=0, supersedes=""):
    STORE["boqs"][bid] = {
        "id": bid, "ref": f"SF/BOQ/26-27/{rev_no:04d}", "fy": "26-27",
        "rev_no": rev_no, "supersedes": supersedes,
        "sections": SECTIONS, "line_items": lines,
    }
    return bid


def test_a_revision_carries_line_ids_forward_unchanged(store):
    """
    The whole point of the identifier: an RA bill raised against revision 1
    still matches its lines after revision 2, even though a revision may
    change quantity, rate, description — and renumber the items.
    """
    rev0 = clean([posted("1"), posted("2")])
    _rev_boq("b0", rev0)

    STORE["ra_bills"]["r1"] = {
        "id": "r1", "boq_id": "b0", "ra_no": 1, "leg": "supply",
        "claims": [ra.build_claim(rev0[0], 4.0, 100.0, 0.0, 100.0)]}
    assert ra.claimed_by_line("b0")[(rev0[0]["line_id"], "supply")] == 4.0

    # Revision 1 posts the same lines back, RENUMBERED, with a new quantity.
    reposted = [dict(posted("24.a", total_qty="30"), line_id=rev0[0]["line_id"]),
                dict(posted("24.b"), line_id=rev0[1]["line_id"]),
                posted("24.c")]                       # a genuinely new line
    rev1 = clean(reposted)
    _rev_boq("b1", rev1, rev_no=1, supersedes="b0")

    assert rev1[0]["line_id"] == rev0[0]["line_id"]   # carried forward
    assert rev1[1]["line_id"] == rev0[1]["line_id"]
    assert rev1[2]["line_id"] not in {rev0[0]["line_id"], rev0[1]["line_id"]}

    # The claim still matches, and now measures against the revised quantity.
    assert ra.claimed_by_line("b1")[(rev0[0]["line_id"], "supply")] == 4.0
    assert ra.approved_by_line("b1")[(rev0[0]["line_id"], "supply")] == 30.0
    assert rev1[0]["item_no"] == "24.a"               # renumbered freely


def test_a_revision_may_not_delete_a_line_that_has_been_claimed(store):
    """
    Deleting a claimed line leaves a claim with no approved quantity behind it:
    the balance arithmetic has nothing to hold and a bill already submitted to
    the main contractor becomes unbacked.
    """
    rev0 = clean([posted("1"), posted("2"), posted("3")])
    _rev_boq("b0", rev0)

    STORE["ra_bills"]["r1"] = {
        "id": "r1", "boq_id": "b0", "ra_no": 1, "leg": "supply",
        "claims": [ra.build_claim(rev0[1], 4.0, 100.0, 0.0, 100.0)]}
    STORE["ra_bills"]["r2"] = {
        "id": "r2", "boq_id": "b0", "ra_no": 3, "leg": "installation",
        "claims": [ra.build_claim(rev0[1], 2.0, 50.0, 0.0, 50.0)]}

    claimed = ra.claims_by_line_id("b0")
    surviving = [rev0[0], rev0[2]]            # line 2 dropped

    blockers = BQ.revision_blockers(rev0, surviving, claimed)
    assert len(blockers) == 1
    assert blockers[0]["item_no"] == "2"
    assert blockers[0]["ra_nos"] == [1, 3]

    msg = BQ.revision_blocker_message(blockers[0])
    assert "Item 2" in msg and "RA1" in msg and "RA3" in msg


def test_a_revision_may_freely_delete_an_unclaimed_line(store):
    rev0 = clean([posted("1"), posted("2")])
    _rev_boq("b0", rev0)

    STORE["ra_bills"]["r1"] = {
        "id": "r1", "boq_id": "b0", "ra_no": 1, "leg": "supply",
        "claims": [ra.build_claim(rev0[0], 4.0, 100.0, 0.0, 100.0)]}

    claimed = ra.claims_by_line_id("b0")
    assert BQ.revision_blockers(rev0, [rev0[0]], claimed) == []


def test_a_zero_quantity_claim_does_not_pin_a_line(store):
    """
    Sparse storage drops zero-quantity rows, but a record written before that
    rule, or one hand-edited, must not lock a line out of ever being removed.
    """
    rev0 = clean([posted("1"), posted("2")])
    _rev_boq("b0", rev0)
    STORE["ra_bills"]["r1"] = {
        "id": "r1", "boq_id": "b0", "ra_no": 1, "leg": "supply",
        "claims": [ra.build_claim(rev0[1], 0.0, 100.0, 0.0, 100.0)]}

    assert ra.claims_by_line_id("b0") == {}
    assert BQ.revision_blockers(rev0, [rev0[0]], ra.claims_by_line_id("b0")) == []


# ═══════════════════════════════════════════════════════════════════════════
# THE DUPLICATE ITEM NUMBER WARNING — surfaced, never acted on
# ═══════════════════════════════════════════════════════════════════════════

def test_the_clients_duplicate_item_number_is_real_and_is_left_alone():
    """
    Section A carries item 17 twice in the client's OWN workbook.

    The generator reads column A verbatim (`tools/gen_demo_data.py:item_no`)
    and its section row ranges do not overlap, so it cannot have invented this:
    21 source rows produced 21 section-A lines, one for one. The seed is a
    faithful copy of the real Sify schedule and stays that way — the identifier
    absorbs the ambiguity, and the form warns about it.
    """
    a17 = [l for l in DD.BOQ_LINES if l["section"] == "A" and l["item_no"] == "17"]
    assert len(a17) == 2
    assert a17[0]["spec"] == "SPR-FLEX-DROP-1500"
    assert a17[1]["spec"] == "VLV-BFLY-CI-150-TS"
    assert a17[0]["line_id"] != a17[1]["line_id"]


def test_a_duplicate_item_number_warns_and_never_blocks():
    """
    It is an ambiguity on the printed sheet, not a billing fault: two lines
    sharing an item number are tracked separately and their claims cannot run
    together. So the save must go through.
    """
    lines, err, idx = BQ._clean_lines(
        [posted("17"), posted("17"), posted("18")], SECTIONS)

    assert err == "" and idx == -1
    assert len(lines) == 3
    assert len({li["line_id"] for li in lines}) == 3


def test_the_form_carries_the_duplicate_item_number_band(client):
    h = client.get("/boq/create").get_data(as_text=True)
    assert 'id="dup-warn"' in h
    assert "function renderDupWarn" in h
    assert ".dup-warn {" in h
    # Amber, per ABOUT.md §5's severity rule — this is "incomplete but
    # working", not "nothing is being saved".
    assert "--saffron" in h.split("function renderDupWarn")[0]


def test_the_band_says_billing_is_unaffected(client):
    """
    The whole point of showing it. Before the line id existed a repeated item
    number silently collapsed two lines into one in the over-claim guard; a
    warning that did not say so would read as "your bill is wrong".
    """
    h = client.get("/boq/create").get_data(as_text=True)
    band = h.split("function renderDupWarn")[1].split("function renderJump")[0]
    assert "does not affect billing" in band
    assert "Saving is not blocked" in band


def test_boq_does_not_import_ra_to_ask_about_claims():
    """
    `revision_blockers()` takes the claim map as an argument rather than
    fetching it, because boq.py may never import ra.py (ABOUT.md §2b) — the
    arrow runs ra -> boq and reversing it is a cycle.
    """
    import ast
    import pathlib

    tree = ast.parse((pathlib.Path(__file__).resolve().parent.parent / "boq.py")
                     .read_text(encoding="utf8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name != "ra" for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "ra"
