"""
A BOQ revision is numbered off its ROOT — 29 October 2026,
CLIENT_CHANGES.md §0 **fifty-ninth** block, B4, from the 28 October 2026
meeting with Yogesh Bankar.

    new revisions are numbered <root ref>/1, /2... (e.g. SF/BOQ/26-27/0019/1)
    and no longer take the next series number. Printed BOQs and anything
    citing the BOQ show the root ref without the suffix. Screens show the
    suffix. Existing revisions keep their numbers. No renumbering of history.
    Stored refs stay unique. Duplicate-BOQ detection and supersedes logic must
    be unaffected. Tests prove both.

⚠ **This is the other half of the 28 October finding `a6ab6c4` fixed.** That
  commit stopped the project page ADDING a chain's revisions together; this
  stops each one spending a fresh series number, which is what made a chain of
  three revisions look like three separate schedules in the client's own book.

The last three sentences are what this file is mostly about: history is not
renumbered, refs stay unique, and every revision guard still refuses what it
refused.
"""

import json

import pytest

import boq as BQ
import pipeline as P
from store import STORE
from test_boq_revisions import _form, clean, _mkbill  # noqa: F401


def _save(client, **kw):
    r = client.post("/boq/create", data=_form(**kw))
    return r


def _a_claimed_bill(boq, ra_no=1, leg="supply", qty=10.0):
    """
    One issued bill claiming the schedule's first line, with its `boq_ref`
    SNAPSHOTTED as the schedule's own ref — suffix and all, which is the
    point of several tests below.
    """
    import uuid
    import ra as RA
    li = boq["line_items"][0]
    claim = RA.build_claim(li, qty, float(li.get("supply_rate") or 0.0), 0.0,
                           float(li.get("supply_rate") or 0.0), leg=leg)
    rid = f"rev-num-{uuid.uuid4().hex[:8]}"
    _mkbill(rid, boq["id"], ra_no, [claim], leg=leg)
    STORE["ra_bills"][rid]["boq_ref"] = boq["ref"]
    STORE["ra_bills"][rid]["boq_rev_no"] = int(boq.get("rev_no") or 0)
    STORE["ra_bills"][rid]["status"] = "issued"
    return rid


def _by_ref():
    return {b["ref"]: b for b in STORE["boqs"].values()}


def _chain(client, n=3):
    """An original plus `n - 1` revisions, oldest first."""
    assert _save(client).status_code == 302
    out = [next(iter(STORE["boqs"].values()))]
    for i in range(1, n):
        r = _save(client, rev_no=str(i), supersedes=out[-1]["id"])
        assert r.status_code == 302, r.get_data(as_text=True)[:600]
        out.append(next(b for b in STORE["boqs"].values()
                        if b["id"] not in {x["id"] for x in out}))
    return out


# ═══ 1. root_ref / rev_suffix — the string rule, and nothing wider ════════

@pytest.mark.parametrize("ref,root,suffix", [
    ("SF/BOQ/26-27/0019",     "SF/BOQ/26-27/0019", ""),
    ("SF/BOQ/26-27/0019/1",   "SF/BOQ/26-27/0019", "1"),
    ("SF/BOQ/26-27/0019/12",  "SF/BOQ/26-27/0019", "12"),
    ("BOQ/26-27/0019/2",      "BOQ/26-27/0019",    "2"),
    # ⚠ Every OTHER number in this application is left alone — none of them
    #   has a second numeric segment, and the pattern requires the remainder
    #   to end in `fy_ref()`'s own 4-or-more-digit tail.
    ("SF/TI/26-27/0001",      "SF/TI/26-27/0001",  ""),
    ("SF/PO/26-27/0001",      "SF/PO/26-27/0001",  ""),
    ("SF/MI/26-27/0001",      "SF/MI/26-27/0001",  ""),
    ("SF/DPO/0001",           "SF/DPO/0001",       ""),
    ("PI-0007",               "PI-0007",           ""),
    ("SF/BOQ/26-27/19/1",     "SF/BOQ/26-27/19/1", ""),   # tail too short
    ("",                      "",                  ""),
    (None,                    "",                  ""),
])
def test_the_suffix_rule_is_exactly_this(ref, root, suffix):
    assert P.root_ref(ref) == root
    assert P.rev_suffix(ref) == suffix


def test_root_ref_is_idempotent():
    assert P.root_ref(P.root_ref("SF/BOQ/26-27/0019/3")) == "SF/BOQ/26-27/0019"


def test_it_lives_beside_the_builder_so_the_two_cannot_disagree():
    # `cap=` is `boq._REF_CAP` (64) — a BOQ number is not Rule 46(b)-capped.
    built = P.fy_ref("SF", "BOQ", "26-27", 19, cap=BQ._REF_CAP)
    assert built == "SF/BOQ/26-27/0019"
    assert P.root_ref(f"{built}/4") == built


# ═══ 2. The minter — <root>/1, /2, and never a series number ══════════════

def test_an_original_still_takes_the_next_series_number(client, clean):
    assert _save(client).status_code == 302
    ref = next(iter(STORE["boqs"].values()))["ref"]
    assert ref.startswith("SF/BOQ/") and P.rev_suffix(ref) == ""


def test_a_revision_is_numbered_off_the_root_and_spends_no_series_number(client, clean):
    a, b, c = _chain(client, 3)
    root = a["ref"]
    assert P.rev_suffix(root) == ""
    assert b["ref"] == f"{root}/1"
    assert c["ref"] == f"{root}/2"
    # ⚠ The series did not move: a second ORIGINAL takes the number the first
    #   revision would have spent under the old behaviour.
    known = {a["id"], b["id"], c["id"]}
    assert _save(client, project="Other job", account="Other party").status_code == 302
    fresh = next(x for x in STORE["boqs"].values() if x["id"] not in known)
    seq_a = int(root.rsplit("/", 1)[1])
    assert int(fresh["ref"].rsplit("/", 1)[1]) == seq_a + 1


def test_revising_a_revision_still_numbers_off_the_ORIGINAL(client, clean):
    a, b, c = _chain(client, 3)
    assert c["ref"] == f"{a['ref']}/2", "it numbered off b, not off the root"
    assert BQ.chain_root(c["id"])["id"] == a["id"]


def test_the_suffix_is_the_smallest_FREE_integer_not_a_count(client, clean):
    """
    ⚠ A revision deleted out of the middle does NOT hand its number back,
    which is the series' own rule one level down.
    """
    a, b, c = _chain(client, 3)
    root = a["ref"]
    assert [b["ref"], c["ref"]] == [f"{root}/1", f"{root}/2"]
    # c is the tip; revise it, then delete that revision and revise again.
    assert _save(client, rev_no="3", supersedes=c["id"]).status_code == 302
    d = next(x for x in STORE["boqs"].values()
             if x["id"] not in {a["id"], b["id"], c["id"]})
    assert d["ref"] == f"{root}/3"
    del STORE["boqs"][d["id"]]
    assert _save(client, rev_no="3", supersedes=c["id"]).status_code == 302
    e = next(x for x in STORE["boqs"].values()
             if x["id"] not in {a["id"], b["id"], c["id"]})
    assert e["ref"] == f"{root}/3", (
        "a deleted revision's number may be reused — it is the smallest FREE "
        "one, and nothing is using /3 any more")


def test_a_chain_whose_ROOT_has_no_usable_ref_falls_back_to_the_series(client, clean):
    """
    A hand-written or imported record with no ref. A revision with no number
    at all is worse than one numbered the old way, so the series is the
    fallback and it is deliberate.
    """
    assert _save(client).status_code == 302
    a = next(iter(STORE["boqs"].values()))
    a["ref"] = ""
    assert _save(client, rev_no="1", supersedes=a["id"]).status_code == 302
    b = next(x for x in STORE["boqs"].values() if x["id"] != a["id"])
    assert b["ref"].startswith("SF/BOQ/26-27/")
    assert P.rev_suffix(b["ref"]) == ""


def test_chain_root_survives_a_cycle_rather_than_hanging():
    STORE["boqs"].clear()
    STORE["boqs"]["x"] = {"id": "x", "ref": "X", "supersedes": "y"}
    STORE["boqs"]["y"] = {"id": "y", "ref": "Y", "supersedes": "x"}
    assert BQ.chain_root("x")["id"] in {"x", "y"}
    STORE["boqs"].clear()


# ═══ 3. Existing revisions keep their numbers — NO renumbering ════════════

def test_a_revision_raised_BEFORE_this_pass_is_never_rewritten(client, clean):
    """
    ⚠ The sentence B4 states twice. A pre-pass revision carries a plain series
    number; nothing in this pass touches it, and `root_ref()` reads it
    correctly by doing nothing.
    """
    a, b = _chain(client, 2)
    # Make b look like a revision raised the OLD way.
    b["ref"] = "SF/BOQ/26-27/0042"
    was = {x["id"]: x["ref"] for x in STORE["boqs"].values()}
    # Everything that reads a chain, and the next revision.
    import ra as RA
    RA.revision_chain(b["id"])
    RA.latest_revision(a["id"])
    client.get(f"/boq/view/{b['id']}")
    client.get(f"/boq/print/{b['id']}")
    client.get("/boq/")
    assert _save(client, rev_no="2", supersedes=b["id"]).status_code == 302
    now = {x["id"]: x["ref"] for x in STORE["boqs"].values()}
    for bid, ref in was.items():
        assert now[bid] == ref, f"{bid} was renumbered"
    assert P.root_ref("SF/BOQ/26-27/0042") == "SF/BOQ/26-27/0042"


def test_the_next_revision_after_an_old_style_one_is_slash_one(client, clean):
    """
    Nothing is using `<root>/1`, so that is what the smallest-free rule gives
    — and it is correct: the suffix counts the numbers in use, not the
    revisions in the chain.
    """
    a, b = _chain(client, 2)
    b["ref"] = "SF/BOQ/26-27/0042"
    assert _save(client, rev_no="2", supersedes=b["id"]).status_code == 302
    c = next(x for x in STORE["boqs"].values() if x["id"] not in {a["id"], b["id"]})
    assert c["ref"] == f"{a['ref']}/1"


# ═══ 4. Stored refs stay unique ═══════════════════════════════════════════

def test_every_stored_ref_is_unique_across_a_long_chain(client, clean):
    chain = _chain(client, 6)
    refs = [x["ref"] for x in STORE["boqs"].values()]
    assert len(refs) == len(set(refs)) == 6
    root = chain[0]["ref"]
    assert sorted(refs) == sorted([root] + [f"{root}/{i}" for i in range(1, 6)])


def test_two_chains_cannot_collide(client, clean):
    a1, b1 = _chain(client, 2)
    assert _save(client, project="Second job", account="Second party").status_code == 302
    a2 = next(x for x in STORE["boqs"].values()
              if x["id"] not in {a1["id"], b1["id"]})
    assert _save(client, rev_no="1", supersedes=a2["id"],
                 project="Second job", account="Second party").status_code == 302
    refs = [x["ref"] for x in STORE["boqs"].values()]
    assert len(refs) == len(set(refs)) == 4
    assert a1["ref"] != a2["ref"]


def test_a_ref_already_in_use_is_skipped_even_if_it_was_written_by_hand(client, clean):
    a, b = _chain(client, 2)
    root = a["ref"]
    assert b["ref"] == f"{root}/1"
    # Somebody writes /2 straight into the store (MySQL, an import).
    STORE["boqs"]["planted"] = {"id": "planted", "ref": f"{root}/2",
                                "supersedes": "", "line_items": [], "rev_no": 0}
    assert _save(client, rev_no="2", supersedes=b["id"]).status_code == 302
    c = next(x for x in STORE["boqs"].values()
             if x["id"] not in {a["id"], b["id"], "planted"})
    assert c["ref"] == f"{root}/3"
    del STORE["boqs"]["planted"]


# ═══ 5. PAPER shows the root; SCREENS show the suffix ═════════════════════

def test_the_printed_schedule_shows_the_root_and_the_revision_row(client, clean):
    a, b = _chain(client, 2)
    page = client.get(f"/boq/print/{b['id']}").get_data(as_text=True)
    assert f'<span class="m-lbl">BOQ No.</span><span class="m-val">{a["ref"]}</span>' in page
    # Which revision it is, is still on the sheet — as the Revision row.
    assert '<span class="m-lbl">Revision</span><span class="m-val">1</span>' in page
    # ⚠ Scoped to the SHEET. The `<title>` keeps the suffix and is right to:
    #   it is the browser tab, which is a screen, and the browser's own header
    #   has not printed since the §0 fifty-third block set `@page margin:0`.
    sheet = page.split('<div class="doc-box">', 1)[1]
    assert b["ref"] not in sheet, "the suffix reached paper"
    assert f"<title>{b['ref']}" in page, "the browser tab lost the suffix"


def test_the_SCREEN_shows_the_suffix(client, clean):
    a, b = _chain(client, 2)
    view = client.get(f"/boq/view/{b['id']}").get_data(as_text=True)
    assert b["ref"] in view, "the screen must say which revision this is"
    register = client.get("/boq/").get_data(as_text=True)
    assert b["ref"] in register and a["ref"] in register


CITING = [
    ("the proforma",        "proformas",         "/proforma/view/{id}"),
    ("the tax invoice",     "invoices",          "/invoice/view/{id}"),
    ("the product inquiry", "purchase_orders",   "/po/print/{id}"),
]


def test_every_document_citing_the_boq_prints_the_root(client, clean):
    """
    ⚠ Eight print sites read a BOQ ref, and all of them go through
    `pipeline.root_ref()`. Asserted on the source as well as on three
    rendered documents, because a ninth site added later would otherwise
    print the suffix and nobody would notice.
    """
    import pathlib
    import re
    repo = pathlib.Path(BQ.__file__).parent
    for mod in ("boq", "proforma", "invoice", "po_draft", "merged_ra",
                "measurement", "ra"):
        src = (repo / f"{mod}.py").read_text(encoding="utf8")
        for m in re.finditer(r'_meta\("(?:Against )?BOQ(?: No\.)?",[^\n]*', src):
            line = m.group(0)
            assert "root_ref(" in line, f"{mod}.py: {line.strip()[:90]}"


def test_a_cited_root_is_what_a_real_document_prints(client, clean):
    import address
    import json as _j
    address.ensure_demo_addresses()
    a, b = _chain(client, 2)
    li = b["line_items"][0]
    vendor = next(x["id"] for x in STORE["addresses"].values()
                  if x.get("type") == "vendor")
    STORE.setdefault("purchase_orders", {}).clear()
    r = client.post(f"/po/create?boq={b['id']}", data={
        "date": "2026-10-29", "vendor_id": vendor, "notes": "",
        "po_json": _j.dumps({"lines": [{"line_id": li["line_id"], "qty": "1"}]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:700]
    pid = next(iter(STORE["purchase_orders"]))
    # The SNAPSHOT keeps the suffix — it is what the schedule was called.
    assert STORE["purchase_orders"][pid]["boq_ref"] == b["ref"]
    sheet = client.get(f"/po/print/{pid}").get_data(as_text=True)
    assert f'<span class="m-val">{a["ref"]}</span>' in sheet
    assert b["ref"] not in sheet
    # And the SCREEN says which revision it was raised against.
    view = client.get(f"/po/view/{pid}").get_data(as_text=True)
    assert b["ref"] in view
    STORE["purchase_orders"].clear()


def test_the_snapshot_keeps_the_suffix_and_only_the_PRINT_strips_it(client, clean):
    """
    ⚠ §1.2. The stored `boq_ref` is what the schedule was CALLED when the
    document was raised, suffix and all; `root_ref()` is a render-time
    display. A migration that rewrote the stored value would lose which
    revision a bill was measured against.
    """
    a, b = _chain(client, 2)
    rid = _a_claimed_bill(b)
    assert STORE["ra_bills"][rid]["boq_ref"] == b["ref"]
    from conftest import printable
    printable(STORE["ra_bills"][rid])
    sheet = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert a["ref"] in sheet and b["ref"] not in sheet


# ═══ 6. The supersedes logic and every revision guard are UNAFFECTED ══════

def test_every_revision_refusal_still_refuses(client, clean):
    a, b = _chain(client, 2)
    before = dict(STORE["boqs"])

    # 1. rev_no above 0 with nothing superseded
    r = _save(client, rev_no="2", supersedes="")
    assert r.status_code == 200 and "no BOQ was chosen" in r.get_data(as_text=True)
    # 2. a predecessor that is already superseded
    r = _save(client, rev_no="1", supersedes=a["id"])
    assert r.status_code == 200
    assert "already been revised" in r.get_data(as_text=True).lower() or \
           "superseded" in r.get_data(as_text=True).lower()
    # 3. a predecessor from another project
    r = _save(client, rev_no="2", supersedes=b["id"], project="Somewhere else")
    assert r.status_code == 200
    # 4. a predecessor that does not exist
    r = _save(client, rev_no="1", supersedes="no-such-id")
    assert r.status_code == 200
    assert "no longer exists" in r.get_data(as_text=True)

    assert dict(STORE["boqs"]) == before, "a refusal wrote something"


def test_the_chain_walkers_are_unaffected_by_the_suffix(client, clean):
    a, b, c = _chain(client, 3)
    ids = {a["id"], b["id"], c["id"]}
    import ra as RA
    for start in (a["id"], b["id"], c["id"]):
        assert set(RA.revision_chain(start)) == ids, start
    assert BQ.superseded_ids() == {a["id"], b["id"]}
    assert BQ.chain_root(c["id"])["id"] == a["id"]


def test_the_tip_is_still_the_tip_and_only_it_offers_revise(client, clean):
    a, b = _chain(client, 2)
    tip = client.get(f"/boq/view/{b['id']}").get_data(as_text=True)
    old = client.get(f"/boq/view/{a['id']}").get_data(as_text=True)
    assert f"/boq/create?revise={b['id']}" in tip
    assert f"/boq/create?revise={a['id']}" not in old


def test_a_claim_against_an_earlier_revision_still_counts(client, clean):
    """
    ⚠ The guard the whole revision mechanism exists for. The suffix is a
    string; `claims_against_chain()` walks ids.
    """
    a, b = _chain(client, 2)
    rid = _a_claimed_bill(a)
    claims = BQ.claims_against_chain(b["id"])
    assert claims, "a claim on the predecessor vanished"
    assert STORE["ra_bills"][rid]["boq_ref"] == a["ref"]


def test_a_revision_dropping_a_claimed_line_is_still_refused(client, clean):
    a, b = _chain(client, 2)
    _a_claimed_bill(b)
    before = dict(STORE["boqs"])
    r = _save(client, rev_no="2", supersedes=b["id"], lines=[
        {"line_id": "bbbbbbbbbbbb", "item_no": "9", "parent_item_no": "",
         "section": "A", "is_header": False, "description": "A different line",
         "remark": "", "unit": "Mtrs", "area_qty": {}, "total_qty": "5",
         "supply_base_rate": "", "supply_escalation_pct": "",
         "supply_rate": "10", "supply_hsn": "", "supply_gst_rate": "18",
         "install_base_rate": "", "install_escalation_pct": "",
         "install_rate": "", "install_sac": "", "install_gst_rate": "18"}])
    assert r.status_code == 200
    assert "already been claimed against" in r.get_data(as_text=True)
    assert dict(STORE["boqs"]) == before


def test_the_duplicate_item_number_warning_still_warns_and_never_blocks(client, clean):
    """
    The other thing "duplicate detection" means on a BOQ: two lines with the
    same item number, which is real in the client's own section A and is
    surfaced rather than refused.
    """
    rows = []
    for lid in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
        rows.append({"line_id": lid, "item_no": "17", "parent_item_no": "",
                     "section": "A", "is_header": False,
                     "description": f"Line {lid[:3]}", "remark": "",
                     "unit": "Mtrs", "area_qty": {}, "total_qty": "1",
                     "supply_base_rate": "", "supply_escalation_pct": "",
                     "supply_rate": "1", "supply_hsn": "", "supply_gst_rate": "18",
                     "install_base_rate": "", "install_escalation_pct": "",
                     "install_rate": "", "install_sac": "", "install_gst_rate": "18"})
    assert _save(client, lines=rows).status_code == 302, "it blocked"
    a = next(iter(STORE["boqs"].values()))
    assert _save(client, rev_no="1", supersedes=a["id"], lines=rows).status_code == 302
    refs = [x["ref"] for x in STORE["boqs"].values()]
    assert len(set(refs)) == 2


def test_the_project_link_still_follows_the_chain_root(client, clean):
    """
    A revision inherits its ancestor's `project_id` and the form cannot
    override it — unchanged by B4, and asserted because the numbering now
    reads the chain root too and the two must not be confused.
    """
    a, b = _chain(client, 2)
    assert b["project_id"] == a["project_id"]


def test_the_series_scan_and_root_ref_agree_about_what_a_suffix_IS(client, clean):
    """
    ⚠ **Two statements of one fact, held in step here.** `series.py` may not
    import `pipeline` (the arrow is refused in
    `tests/test_import_directions.py`, and the leaf does no formatting), so
    `Series.segments` says "a ref with a segment after the ordinal is a
    revision" as a COUNT while `pipeline.root_ref()` says it as a pattern.
    If they ever disagree, the next original's number moves silently.
    """
    import series as SER
    s = SER.BY_KEY["BOQ"]
    for ref in ("SF/BOQ/26-27/0019", "BOQ/26-27/0019", "SF/TI/26-27/0001",
                "SF/BOQ/26-27/0019/1", "SF/BOQ/26-27/0019/25"):
        by_count = len(ref.split("/")) > s.segments
        by_pattern = P.rev_suffix(ref) != ""
        assert by_count == by_pattern, ref


def test_a_long_chain_does_not_push_the_series_forward(client, clean):
    """
    ⚠ The defect the segment rule prevents, stated as a test rather than as a
    comment. Without it, `/0001/1` … `/0001/6` scanned naively give a max of
    6, and the next ORIGINAL becomes `0007` — five numbers skipped out of the
    client's own book.
    """
    chain = _chain(client, 6)
    root = chain[0]["ref"]
    assert chain[-1]["ref"] == f"{root}/5"
    known = {x["id"] for x in chain}
    assert _save(client, project="Another job",
                 account="Another party").status_code == 302
    fresh = next(x for x in STORE["boqs"].values() if x["id"] not in known)
    seq_root = int(root.rsplit("/", 1)[1])
    assert int(fresh["ref"].rsplit("/", 1)[1]) == seq_root + 1, (
        "the revision suffixes pushed the series forward")


# ═══ 7. No golden moved, and why ═══════════════════════════════════════════

def test_root_ref_is_a_no_op_on_every_pinned_document(client):
    """
    ⚠ Why B4 moved NO print golden: every pinned record is an ORIGINAL, so
    `root_ref()` returns its ref unchanged. Stated as an assertion so a later
    pass that pins a REVISION has to re-measure deliberately.
    """
    from test_print_golden import GOLD_DPO
    import test_print_golden as TPG
    for ref in ("SF/BOQ/26-27/0001", "SF/BOQ/26-27/0007"):
        assert P.root_ref(ref) == ref
    client.get("/boq/")
    for b in STORE["boqs"].values():
        assert P.rev_suffix(b["ref"]) == "" or b.get("supersedes"), (
            "a seeded BOQ carries a revision suffix without being a revision")
