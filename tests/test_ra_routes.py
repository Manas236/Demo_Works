"""
The RA entry form, and the lifecycle lock.

The routes that make an RA bill enterable: the blueprint, the create form, the
edit route gated to a draft that is also the latest bill, the POST-only delete,
and the issue/cancel pair that replaced certification.

Three properties everything here circles:

- **The block is hard, and it is CUMULATIVE.** Per-bill would pass nine times
  and still end 9% over. It counts drafts and issued bills and excludes
  cancelled ones.
- **The claim freezes twice over.** Once by POSITION (a later bill exists) and
  once by STATUS (it has been issued). Neither implies the other.
- **A cancelled number is spent.** Cancelled RA3 stays RA3 and the next bill is
  RA4, the same reasoning that stops a GST serial being reissued.
"""

import json

import pytest

import boq as BQ
import demo_data as DD
import ra
from store import STORE
from conftest import chain_ready, printable
import approval


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(client):
    """The real 97-line Sify BOQ, seeded through the app."""
    STORE["ra_bills"].clear()
    BQ.ensure_demo_boq()
    # CC-2 C1 — the order of working, enforced by URL from 29 August 2026.
    # Every test in this file is about the BILL and not about the chain, so the
    # fixture describes a project a claim can actually be raised on. Read
    # `conftest.chain_ready()` for why it writes the two records directly.
    chain_ready(DD.BOQ_META["id"])
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()


def priced(boq_id, n=None):
    lines = [li for li in STORE["boqs"][boq_id]["line_items"]
             if not li["is_header"] and li["total_qty"] > 0]
    return lines[:n] if n else lines


def payload(rows):
    """rows: [(line_id, qty, rate)] -> the hidden field's JSON."""
    return json.dumps({"lines": [{"line_id": lid, "qty": str(q), "rate": str(r)}
                                 for lid, q, r in rows]})


def make_bill(boq_id, ra_no, leg="supply", claims=None, **over):
    rid = f"r{ra_no}-{leg}"
    subtotal, drows, dtotal, net = ra.bill_totals(claims or [], [])
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-06", "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "ra_no": ra_no, "leg": leg, "claims": claims or [],
        "claim_subtotal": subtotal, "deductions": drows,
        "deduction_total": dtotal, "net_payable": net,
        # A DRAFT by default, so the edit and delete tests below exercise the
        # position gate rather than tripping over the status gate first. Tests
        # that want an issued or cancelled bill pass `status=` through `**over`.
        "status": "draft", "issued_on": "", "cancelled_on": "",
        "cancel_reason": "", "notes": "",
    }
    STORE["ra_bills"][rid].update(over)
    return rid


def claim_for(li, qty, rate=None, prev=0.0):
    r = li["supply_rate"] if rate is None else rate
    return ra.build_claim(li, qty, r, prev, li["supply_rate"])


# ═══════════════════════════════════════════════════════════════════════════
# THE BLUEPRINT — and the /boq/view 500 it closes
# ═══════════════════════════════════════════════════════════════════════════

def test_the_ra_blueprint_is_registered(client):
    import app as app_module
    assert "ra" in app_module.app.blueprints
    rules = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    for endpoint in ("ra.create_ra", "ra.view_ra", "ra.edit_ra", "ra.delete_ra"):
        assert endpoint in rules


def test_boq_view_renders_when_an_ra_bill_exists(client, seeded):
    """
    THE regression. `boq.view_boq()` builds `url_for("ra.view_ra", …)` for every
    RA bill against the BOQ, so before the blueprint was registered this raised
    BuildError and returned 500 — but only once a bill existed, which nothing
    could create. Registering the blueprint is what closes it.

    This test fails with a 500 if the blueprint is ever unregistered.
    """
    li = priced(seeded, 1)[0]
    make_bill(seeded, 1, claims=[claim_for(li, 1.0)])

    r = client.get(f"/boq/view/{seeded}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "RA1" in body
    assert f"/ra/view/r1-supply" in body


# ═══════════════════════════════════════════════════════════════════════════
# THE CREATE FORM
# ═══════════════════════════════════════════════════════════════════════════

def test_the_picker_lists_boqs_and_offers_both_legs(client, seeded):
    h = client.get("/ra/create").get_data(as_text=True)
    assert "SF/BOQ/26-27/0001" in h
    assert "leg=supply" in h and "leg=installation" in h


def test_the_form_shows_every_boq_line_not_a_shortlist(client, seeded):
    """
    All lines, in BOQ order, claim qty defaulting to 0.

    The operator works from a site measurement sheet against item numbers, not
    from a filtered view — and hiding an exhausted line hides the fact that it
    is exhausted, which is the state most likely to be mis-claimed.
    """
    h = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    lines = STORE["boqs"][seeded]["line_items"]

    for li in lines:
        if li["is_header"]:
            continue
        assert f'id="row_{li["line_id"]}"' in h, f'{li["item_no"]} missing'
        assert f'id="q_{li["line_id"]}"' in h

    # In BOQ order.
    ids = [li["line_id"] for li in lines if not li["is_header"]]
    positions = [h.index(f'id="row_{i}"') for i in ids]
    assert positions == sorted(positions)


def test_an_exhausted_line_is_shown_not_hidden(client, seeded):
    li = priced(seeded, 1)[0]
    make_bill(seeded, 1, claims=[claim_for(li, li["total_qty"])])

    h = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert f'id="row_{li["line_id"]}"' in h
    assert "cl-done" in h            # greyed, with its balance called out


def test_saving_assigns_the_ra_number_server_side(client, seeded):
    """
    The user never types it, which is what makes "RA5 before RA4" and "two
    RA6s" impossible rather than merely rejected.
    """
    lines = priced(seeded, 2)
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06", "notes": "",
        "ra_json": payload([(lines[0]["line_id"], 1, lines[0]["supply_rate"])]),
    })
    assert r.status_code == 302
    bill = next(iter(STORE["ra_bills"].values()))
    assert bill["ra_no"] == 1
    assert bill["leg"] == "supply"
    assert bill["ref"].startswith("SF/RA/")

    # A second bill takes 2, whatever leg it is on — one series per project.
    client.post(f"/ra/create?boq={seeded}&leg=installation", data={
        "date": "2026-08-06",
        "ra_json": payload([(lines[1]["line_id"], 1, lines[1]["install_rate"])]),
    })
    assert sorted(b["ra_no"] for b in STORE["ra_bills"].values()) == [1, 2]


def test_a_bill_carries_exactly_one_leg(client, seeded):
    """
    Mixed-leg is impossible by CONSTRUCTION, not discouraged by the UI: the leg
    is a property of the bill and a claim row has no leg field of its own, so
    there is no shape in which a mixed bill can be expressed.
    """
    li = priced(seeded, 1)[0]
    client.post(f"/ra/create?boq={seeded}&leg=installation", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], 1, li["install_rate"])]),
    })
    bill = next(iter(STORE["ra_bills"].values()))
    assert bill["leg"] == "installation"
    assert all("leg" not in c for c in bill["claims"])


def test_an_unknown_leg_falls_back_and_never_invents_a_third(client, seeded):
    h = client.get(f"/ra/create?boq={seeded}&leg=nonsense").get_data(as_text=True)
    assert "supply" in h
    assert "nonsense" not in h


def test_zero_quantity_lines_are_dropped_on_save(client, seeded):
    """
    Sparse storage, complete display. An untouched line must never assert a
    claim of zero it did not make, and dropping them keeps `ra_bills` small and
    `claimed_by_line()` cheap.
    """
    lines = priced(seeded, 5)
    rows = [(li["line_id"], 0, li["supply_rate"]) for li in lines]
    rows[2] = (lines[2]["line_id"], 3, lines[2]["supply_rate"])

    client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06", "ra_json": payload(rows)})

    bill = next(iter(STORE["ra_bills"].values()))
    assert len(bill["claims"]) == 1
    assert bill["claims"][0]["line_id"] == lines[2]["line_id"]


def test_a_claim_for_a_line_not_in_the_boq_is_refused(client, seeded):
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(BQ._new_line_id(), 5, 100)])})

    assert r.status_code == 200                  # re-rendered, not saved
    assert "not in the approved BOQ" in r.get_data(as_text=True)
    assert STORE["ra_bills"] == {}


def test_a_claim_with_nothing_on_it_is_refused(client, seeded):
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06", "ra_json": json.dumps({"lines": []})})
    assert "Nothing has been claimed" in r.get_data(as_text=True)
    assert STORE["ra_bills"] == {}


def test_a_rejected_post_returns_the_operators_figures(client, seeded):
    """
    The always-return-the-user's-input contract. Re-entering 80 lines because
    one was over is not a thing anybody should be asked to do.
    """
    lines = priced(seeded, 3)
    over = lines[0]
    rows = [(over["line_id"], over["total_qty"] + 5, over["supply_rate"]),
            (lines[1]["line_id"], 2, 4321.0)]

    h = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06", "ra_json": payload(rows)}).get_data(as_text=True)

    assert f'id="q_{lines[1]["line_id"]}"' in h
    assert "4321" in h                            # the typed rate came back
    assert str(over["total_qty"] + 5) in h        # and so did the bad one


# ═══════════════════════════════════════════════════════════════════════════
# THE BLOCK, THROUGH THE FORM
# ═══════════════════════════════════════════════════════════════════════════

def test_an_overclaim_is_blocked_with_the_whole_arithmetic(client, seeded):
    li = priced(seeded, 1)[0]
    h = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], li["total_qty"] + 3, li["supply_rate"])]),
    }).get_data(as_text=True)

    assert STORE["ra_bills"] == {}
    assert f'Item {li["item_no"]}' in h
    assert "approved" in h and "over" in h


def test_the_block_is_cumulative_across_bills_not_per_bill(client, seeded):
    """
    A per-bill check passes nine times and still ends 9% over. Their own sheet
    is nine RA runs against one schedule.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    half = li["total_qty"] / 2

    make_bill(seeded, 1, claims=[claim_for(li, half)])

    # The same quantity again is fine — it exactly exhausts the line.
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], half, li["supply_rate"])])})
    assert r.status_code == 302

    # One more unit is not.
    h = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], 1, li["supply_rate"])])
    }).get_data(as_text=True)
    assert "already claimed on earlier RA bills" in h


def test_the_two_legs_do_not_block_each_other(client, seeded):
    li = next(x for x in priced(seeded)
              if x["total_qty"] > 0 and x["install_rate"] > 0)
    make_bill(seeded, 1, leg="supply", claims=[claim_for(li, li["total_qty"])])

    r = client.post(f"/ra/create?boq={seeded}&leg=installation", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], li["total_qty"], li["install_rate"])])})
    assert r.status_code == 302


def test_a_diverging_rate_warns_and_never_blocks(client, seeded):
    """Rates legitimately move on approved variations — ten cells of the
    client's own annexure do."""
    li = priced(seeded, 1)[0]
    odd = li["supply_rate"] + 250.0

    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], 1, odd)])})
    assert r.status_code == 302

    bill = next(iter(STORE["ra_bills"].values()))
    assert bill["claims"][0]["rate_varies"] is True
    assert bill["claims"][0]["rate"] == odd

    h = client.get(f'/ra/view/{bill["id"]}').get_data(as_text=True)
    assert "differs from the approved BOQ" in h


def test_a_negative_quantity_is_refused(client, seeded):
    li = priced(seeded, 1)[0]
    h = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], -5, li["supply_rate"])])
    }).get_data(as_text=True)
    assert "negative" in h
    assert STORE["ra_bills"] == {}


# ═══════════════════════════════════════════════════════════════════════════
# THE CAPS — enforced here, never in the persistence layer
# ═══════════════════════════════════════════════════════════════════════════

def test_the_line_cap_is_derived_from_the_boqs():
    """
    The form renders every line of the approved BOQ, so a BOQ that is legal at
    600 lines must produce an RA post that is legal at 600 lines.
    """
    assert ra.MAX_RA_LINES == BQ.MAX_LINES


def test_the_byte_cap_is_measured_not_copied():
    """An RA line carries no spec text, so boq's budget is the wrong budget."""
    assert ra.MAX_RA_JSON_BYTES == 150_000
    assert ra.MAX_RA_JSON_BYTES < BQ.MAX_JSON_BYTES


def test_the_real_97_line_boq_posts_far_inside_the_cap(seeded):
    """The measurement the constant was set from: ~79 B/line, 87 lines."""
    lines = priced(seeded)
    raw = payload([(li["line_id"], li["total_qty"], li["supply_rate"])
                   for li in lines])
    assert len(raw) < ra.MAX_RA_JSON_BYTES / 10
    assert len(raw) / len(lines) < 120


def test_an_oversized_payload_is_rejected_by_the_form(client, seeded):
    li = priced(seeded, 1)[0]
    boq = STORE["boqs"][seeded]
    claims, err, _bad = ra.clean_claims(
        [{"line_id": li["line_id"], "qty": "1", "rate": "1"}],
        boq, "supply", {}, payload_bytes=ra.MAX_RA_JSON_BYTES + 1)
    assert claims == []
    assert "too large to save" in err


def test_too_many_lines_is_rejected_by_the_form(seeded):
    boq = STORE["boqs"][seeded]
    rows = [{"line_id": BQ._new_line_id(), "qty": "1", "rate": "1"}
            for _ in range(ra.MAX_RA_LINES + 1)]
    claims, err, _bad = ra.clean_claims(rows, boq, "supply", {})
    assert claims == []
    assert "limit is" in err


# ═══════════════════════════════════════════════════════════════════════════
# MUTABILITY — the POSITION gate. The status gate is the next section.
# ═══════════════════════════════════════════════════════════════════════════

def test_the_latest_bill_can_be_edited(client, seeded):
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])

    assert ra.claim_is_frozen(STORE["ra_bills"][rid]) is False
    assert client.get(f"/ra/edit/{rid}").status_code == 200

    r = client.post(f"/ra/edit/{rid}", data={
        "date": "2026-08-07",
        "ra_json": payload([(li["line_id"], 4, li["supply_rate"])])})
    assert r.status_code == 302
    assert STORE["ra_bills"][rid]["claims"][0]["qty"] == 4.0


def test_a_bill_with_a_later_bill_after_it_cannot_have_its_claim_edited(client, seeded):
    """
    `claimed_by_line()` sums the whole chain, so editing a mid-chain bill
    silently changes every downstream balance — including ones already printed
    and handed to the main contractor.
    """
    lines = priced(seeded, 2)
    first = make_bill(seeded, 1, claims=[claim_for(lines[0], 1.0)])
    make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])

    assert ra.claim_is_frozen(STORE["ra_bills"][first]) is True

    r = client.get(f"/ra/edit/{first}")
    assert r.status_code == 302                    # bounced to the view
    assert "/ra/view/" in r.headers["Location"]

    before = STORE["ra_bills"][first]["claims"][0]["qty"]
    client.post(f"/ra/edit/{first}", data={
        "date": "2026-08-07",
        "ra_json": payload([(lines[0]["line_id"], 99, 1)])})
    assert STORE["ra_bills"][first]["claims"][0]["qty"] == before


def test_editing_excludes_the_bills_own_figures_from_the_block(client, seeded):
    """
    Otherwise a bill claiming the full approved quantity could never be saved
    again — it would block against itself.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    rid = make_bill(seeded, 1, claims=[claim_for(li, li["total_qty"])])

    r = client.post(f"/ra/edit/{rid}", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], li["total_qty"], li["supply_rate"])])})
    assert r.status_code == 302
    assert STORE["ra_bills"][rid]["claims"][0]["qty"] == li["total_qty"]


def test_the_frozen_reason_names_the_bills_that_froze_it(seeded):
    lines = priced(seeded, 3)
    first = make_bill(seeded, 1, claims=[claim_for(lines[0], 1.0)])
    make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])
    make_bill(seeded, 5, claims=[claim_for(lines[2], 1.0)])

    why = ra.frozen_reason(STORE["ra_bills"][first])
    assert "RA2" in why and "RA5" in why
    assert "already sent out" in why


# ═══════════════════════════════════════════════════════════════════════════
# THE LIFECYCLE — the lock that replaced certification
# ═══════════════════════════════════════════════════════════════════════════

def test_issuing_a_bill_shuts_the_claim_and_the_delete(client, seeded):
    """
    THE lock. Certification used to provide this as a side effect of being a
    status; it is now the status's actual job, and both halves have to shut
    together — an issued bill that could still be deleted would be a document
    the main contractor holds and we do not.
    """
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    bill = STORE["ra_bills"][rid]

    assert ra.can_edit(bill)[0] is True         # a draft, and the latest
    assert ra.can_delete(bill)[0] is True

    r = client.post(f"/ra/issue/{rid}", data={"issued_on": "2026-08-15"})
    assert r.status_code == 302
    assert bill["status"] == "issued"
    assert bill["issued_on"] == "2026-08-15"

    assert ra.can_edit(bill)[0] is False
    assert ra.can_delete(bill)[0] is False

    # And the routes refuse, not just the predicates.
    assert client.get(f"/ra/edit/{rid}").status_code == 302
    client.post(f"/ra/delete/{rid}")
    assert rid in STORE["ra_bills"]


def test_issuing_moves_no_figure_on_the_bill(client, seeded):
    """`apply_issue()` writes two keys and nothing else, so "issuing does not
    restate a claim" is true by construction rather than by a check."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=100.0)])
    bill = STORE["ra_bills"][rid]
    before = {k: v for k, v in bill.items()
              if k not in ("status", "issued_on")}

    client.post(f"/ra/issue/{rid}")

    for k, v in before.items():
        assert bill[k] == v, f"issuing rewrote {k}"


def test_a_get_on_issue_changes_nothing(client, seeded):
    """
    §7.9f's `url_map` sweep only walks rules whose path contains "delete", so it
    does not cover this route at all. Its own test, per the standing rule.
    """
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])

    r = client.get(f"/ra/issue/{rid}")
    assert r.status_code == 200                        # the confirmation page
    assert STORE["ra_bills"][rid]["status"] == "draft"  # untouched
    assert "confirm(" not in r.get_data(as_text=True)   # no browser dialog


def test_a_get_on_cancel_changes_nothing(client, seeded):
    """Same rule, same reason — and cancelling is the irreversible one."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)], status="issued")

    r = client.get(f"/ra/cancel/{rid}")
    assert r.status_code == 200
    assert STORE["ra_bills"][rid]["status"] == "issued"
    assert "confirm(" not in r.get_data(as_text=True)


def test_cancelling_needs_a_reason_and_records_it(client, seeded):
    """
    A cancelled RA number stays spent forever, so the reason is the only thing
    that will ever explain the gap in the run.
    """
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)], status="issued")

    r = client.post(f"/ra/cancel/{rid}", data={"cancel_reason": ""})
    assert r.status_code == 200                          # re-rendered, refused
    assert STORE["ra_bills"][rid]["status"] == "issued"
    assert "Say why" in r.get_data(as_text=True)

    r = client.post(f"/ra/cancel/{rid}", data={"cancel_reason": "remeasured",
                                               "cancelled_on": "2026-08-15"})
    assert r.status_code == 302
    bill = STORE["ra_bills"][rid]
    assert bill["status"] == "cancelled"
    assert bill["cancel_reason"] == "remeasured"
    assert bill["cancelled_on"] == "2026-08-15"


def test_a_cancelled_bill_cannot_be_un_cancelled_edited_or_deleted(client, seeded):
    """There is no route back. An un-cancel would make the withdrawal something
    that could be quietly taken back."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)],
                    status="cancelled", cancelled_on="2026-08-15",
                    cancel_reason="keyed twice")
    bill = STORE["ra_bills"][rid]

    assert ra.can_issue(bill)[0] is False
    assert ra.can_cancel(bill)[0] is False
    assert ra.can_edit(bill)[0] is False
    assert ra.can_delete(bill)[0] is False

    for url in (f"/ra/issue/{rid}", f"/ra/cancel/{rid}", f"/ra/edit/{rid}"):
        assert client.post(url, data={"cancel_reason": "x"}).status_code == 302
    client.post(f"/ra/delete/{rid}")

    assert STORE["ra_bills"][rid]["status"] == "cancelled"
    assert rid in STORE["ra_bills"]


def test_the_ra_number_is_never_reused_after_a_cancellation(client, seeded):
    """
    Cancelled RA3 stays RA3 and the next bill is RA4 — a GST serial's rule.
    This is the whole reason cancelling exists alongside deleting: a delete
    frees the number, a cancel spends it.
    """
    lines = priced(seeded, 4)
    for n in (1, 2, 3):
        make_bill(seeded, n, claims=[claim_for(lines[n - 1], 1.0)],
                  status="issued")

    r = client.post("/ra/cancel/r3-supply", data={"cancel_reason": "withdrawn"})
    assert r.status_code == 302
    assert STORE["ra_bills"]["r3-supply"]["status"] == "cancelled"

    assert ra.next_ra_no(seeded) == 4        # NOT 3


def test_a_draft_prints_with_a_marker_and_an_issued_bill_prints_clean(client, seeded):
    """
    The whole risk is a working copy reaching the main contractor's desk looking
    like a live tax invoice, so the marker is on the printed sheet and not
    behind a `@media screen`.
    """
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])

    # ⚠ **Extended 29 August 2026 for CC-2 B7, and the collision is asserted
    #   here rather than smoothed over.** The fixture line above stood as:
    #
    #       rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    #       h = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    #
    #   — a draft, printed. B7 is unqualified: "an unapproved document may be
    #   viewed, but not printed or downloaded", and a draft is unapproved. So
    #   **the printed DRAFT working copy this test exists for is now gated**,
    #   which is a real loss taken deliberately and recorded in ABOUT.md §2i.
    #
    #   Every assertion below is unchanged and still runs. What is added is the
    #   refusal itself, first, so the new rule is pinned by the same test that
    #   pins what it took away — rather than the loss being visible only as a
    #   fixture that quietly gained a field.
    #
    # ⚠ **REVERSED the same day, 29 August 2026, by the FIFTH override block.**
    #   The loss above was taken back: B7 is narrowed to admit `draft` and
    #   `cancelled` and nothing else, because the DRAFT overprint this test
    #   exists for is itself the safeguard B7 wants. The two lines that were
    #   added that morning, kept verbatim so the reversal is legible:
    #
    #       refused = client.get(f"/ra/print/{rid}", follow_redirects=False)
    #       assert refused.status_code in (302, 303), (
    #           "B7 no longer refuses to print an unapproved draft")
    #
    #       approval.clear_approvals(STORE["ra_bills"][rid])
    #       printable(STORE["ra_bills"][rid])
    #
    #   What replaces them is the assertion that the draft prints WITHOUT being
    #   made approvable first — which is the exemption, stated positively. The
    #   `printable()` helper is deliberately not called: if the exemption ever
    #   goes away, this fails rather than passing for the wrong reason.
    #   `tests/test_approval_b7.py` holds the same rule from the other side and
    #   asserts the overprint on a rejected draft too.
    assert approval.status_of(STORE["ra_bills"][rid]) == approval.PENDING, (
        "this bill must be UNAPPROVED for the exemption to be what is under "
        "test")

    h = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "DRAFT" in h
    assert "has not been issued" in h

    client.post(f"/ra/issue/{rid}")
    # ⚠ An ISSUED bill is NOT exempt — that is the case B7 is about, and the
    #   narrowing does not reach it. So the second half of this test, which is
    #   about the document rather than the ladder, has to describe a bill that
    #   can be printed. `printable()` is what says so in one place.
    printable(STORE["ra_bills"][rid])
    h = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "DRAFT" not in h
    # The stylesheet still DEFINES .lc-mark — it is one sheet for all three
    # states. What must be absent is the element.
    assert '<div class="lc-mark' not in h
    assert '<div class="lc-band' not in h


def test_a_cancelled_bill_still_prints_over_a_cancelled_overprint(client, seeded):
    """Cancelling is not deleting: the record survives and still prints, because
    it is the record of what was withdrawn."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)],
                    status="cancelled", cancelled_on="2026-08-15",
                    cancel_reason="superseded by RA2")
    # ⚠ CC-2 B7 (29 August 2026). The fixture call above is unchanged; what is
    #   added is `approval_status`. A cancelled bill is unapproved, so B7 gates
    #   it too — and "cancelling is not deleting: the record survives and still
    #   prints" is a property this repo decided deliberately (ra.py's lifecycle)
    #   which B7 now qualifies. The assertions below are untouched and still
    #   pin the CANCELLED overprint; the collision is recorded in ABOUT.md §2i
    #   and carried into the pass report as an open question for the client.
    #
    # ⚠ **REVERSED the same day by the FIFTH override block**, which readmits a
    #   cancelled bill: it is not a claim, it is the audit record of a withdrawn
    #   one, and a record that cannot be produced is not a record. The line
    #   added that morning, kept verbatim:
    #
    #       printable(STORE["ra_bills"][rid])
    #
    #   It is gone, and its absence is the assertion: this bill is unapproved
    #   and prints anyway.
    assert approval.status_of(STORE["ra_bills"][rid]) == approval.PENDING, (
        "this bill must be UNAPPROVED for the exemption to be what is under "
        "test")

    r = client.get(f"/ra/print/{rid}")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert "CANCELLED" in h
    assert "superseded by RA2" in h
    assert "not reissued" in h


# ═══════════════════════════════════════════════════════════════════════════
# THE OVER-CLAIM GUARD UNDER THE NEW STATES
# ═══════════════════════════════════════════════════════════════════════════

def test_two_drafts_claiming_the_same_remaining_quantity_are_both_caught(
        client, seeded):
    """
    THE case that made drafts count. A draft is not yet a document, but its
    quantity is committed the moment it is saved — if the sum ignored drafts,
    two of them could each claim the whole remaining balance of a line and the
    guard would see nothing until the second was issued, by which point the
    first has already been sent.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    full = li["total_qty"]

    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], full, li["supply_rate"])])})
    assert r.status_code == 302                       # the first one saves
    first = next(iter(STORE["ra_bills"].values()))
    assert first["status"] == "draft"                 # still only a draft

    # The second, claiming the same quantity again, is REFUSED — while the
    # first is still nothing but a draft.
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], full, li["supply_rate"])])})
    assert r.status_code == 200                       # re-rendered with the block
    assert "over" in r.get_data(as_text=True).lower()
    assert len(STORE["ra_bills"]) == 1                # nothing was written

    # And at the level the guard actually works at:
    assert ra.claimed_by_line(seeded)[(li["line_id"], "supply")] == full


def test_cancelling_a_bill_releases_its_quantity_back(client, seeded):
    """
    The other half. A withdrawn claim is not competing for the approved
    quantity, so cancelling must put it back — otherwise every mistake anybody
    ever cancelled would sterilise its quantity forever.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    full = li["total_qty"]
    rid = make_bill(seeded, 1, claims=[claim_for(li, full)], status="issued")
    key = (li["line_id"], "supply")

    assert ra.claimed_by_line(seeded)[key] == full
    # Nothing more can be claimed against the line.
    assert len(ra.overclaims(seeded, "supply", [claim_for(li, 1.0)])) == 1

    r = client.post(f"/ra/cancel/{rid}", data={"cancel_reason": "remeasured"})
    assert r.status_code == 302

    assert ra.claimed_by_line(seeded).get(key, 0.0) == 0.0
    assert ra.overclaims(seeded, "supply", [claim_for(li, full)]) == []


def test_a_cancelled_bill_is_outstanding_nothing(seeded):
    """Excluded from outstanding as well as from the claim sum — carrying its
    value forward would state a debt on a document we have said is void."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=100.0)],
                    grand_total=236.0, status="issued")
    bill = STORE["ra_bills"][rid]

    assert ra.outstanding_of(bill) == 236.0
    ra.apply_cancel(bill, "withdrawn", on="2026-08-15")
    assert ra.outstanding_of(bill) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# RECEIPTS — only against an ISSUED bill
# ═══════════════════════════════════════════════════════════════════════════

def test_a_receipt_may_only_be_recorded_against_an_issued_bill(client, seeded):
    """
    A draft has not been sent, so there is nothing for the main contractor to
    have paid; a cancelled bill is owed nothing. Refused at the route, with the
    reason in words, and the control on `/ra/view` disabled from the same
    function so the two cannot say different things.
    """
    STORE["receipts"].clear()
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=100.0)],
                    grand_total=236.0)
    bill = STORE["ra_bills"][rid]

    assert ra.can_receipt(bill)[0] is False
    assert "still a draft" in ra.can_receipt(bill)[1]

    r = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-15", "amount": "100", "mode": "neft"})
    assert r.status_code == 200                     # re-rendered, refused
    assert STORE["receipts"] == {}

    # Issue it, and the same post lands.
    client.post(f"/ra/issue/{rid}")
    assert ra.can_receipt(bill)[0] is True
    r = client.post(f"/receipt/new?ra={rid}", data={
        "date": "2026-08-15", "amount": "100", "mode": "neft"})
    assert r.status_code == 302
    assert len(STORE["receipts"]) == 1
    STORE["receipts"].clear()


def test_cancelling_a_bill_with_receipts_is_refused(client, seeded):
    """
    In the same shape as `can_delete()`'s refusal, and for the same reason:
    cancelling would state that nothing is owed on a document money has already
    been paid against, and drop that bill out of the ledger's arithmetic.
    """
    STORE["receipts"].clear()
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=100.0)],
                    grand_total=236.0, status="issued")
    STORE["receipts"]["rc1"] = {
        "id": "rc1", "ref": "SF/RCPT/26-27/0001", "fy": "26-27",
        "date": "2026-08-15", "ra_id": rid, "amount": 100.0, "mode": "neft",
    }

    allowed, why = ra.can_cancel(STORE["ra_bills"][rid])
    assert allowed is False
    assert "receipt" in why.lower()

    r = client.post(f"/ra/cancel/{rid}", data={"cancel_reason": "x"})
    assert r.status_code == 302
    assert STORE["ra_bills"][rid]["status"] == "issued"   # unchanged
    STORE["receipts"].clear()


# ═══════════════════════════════════════════════════════════════════════════
# DELETE — a draft, latest only, POST only
# ═══════════════════════════════════════════════════════════════════════════

def test_the_latest_bill_can_be_deleted_and_the_number_is_reused(client, seeded):
    """
    After a delete the next bill takes max+1 from what remains, so the sequence
    stays contiguous and a number the client has already seen is never
    reissued under different figures.
    """
    lines = priced(seeded, 2)
    make_bill(seeded, 1, claims=[claim_for(lines[0], 1.0)])
    second = make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])

    assert ra.can_delete(STORE["ra_bills"][second])[0] is True
    r = client.post(f"/ra/delete/{second}")
    assert r.status_code == 302
    assert second not in STORE["ra_bills"]
    assert ra.next_ra_no(seeded) == 2


def test_a_get_never_deletes_anything(client, seeded):
    """No GET path in this app destroys anything — a link that deletes is a
    link a crawler, a prefetch or a back button can fire."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])

    r = client.get(f"/ra/delete/{rid}")
    assert r.status_code == 200                # the confirmation page
    assert rid in STORE["ra_bills"]            # still there


def test_the_confirmation_page_names_the_bill_and_the_total(client, seeded):
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=1000.0)])

    h = client.get(f"/ra/delete/{rid}").get_data(as_text=True)
    assert "RA1" in h
    assert "2,000.00" in h                     # the claimed total being removed
    assert "cannot be undone" in h


def test_a_mid_chain_bill_cannot_be_deleted(client, seeded):
    lines = priced(seeded, 2)
    first = make_bill(seeded, 1, claims=[claim_for(lines[0], 1.0)])
    make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])

    allowed, why = ra.can_delete(STORE["ra_bills"][first])
    assert allowed is False
    assert "RA2" in why

    r = client.post(f"/ra/delete/{first}")
    assert r.status_code == 302
    assert first in STORE["ra_bills"]


def test_an_issued_bill_is_never_deleted(client, seeded):
    """
    It has been out of the building. A document that has gone out is withdrawn
    by CANCELLING it — which keeps the number spent and records why — never by
    removing it from our own books.

    (This replaces `test_a_bill_carrying_certification_is_never_deleted`, which
    pinned the same property through the field that used to carry it.)
    """
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=100.0)],
                    status="issued")

    allowed, why = ra.can_delete(STORE["ra_bills"][rid])
    assert allowed is False
    assert "issued" in why.lower()
    assert "cancel" in why.lower()          # it names the remedy

    client.post(f"/ra/delete/{rid}")
    assert rid in STORE["ra_bills"]


def test_the_delete_refusal_is_shown_not_hidden(client, seeded):
    """Refuse with a message saying why; a control that vanishes teaches
    nothing about why."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 2.0, rate=100.0)],
                    status="issued")

    h = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "Delete" in h                            # the button is still there
    assert "cannot be deleted" in h                 # with the reason on it


# ═══════════════════════════════════════════════════════════════════════════
# THE item_no SNAPSHOT — a revision must not rewrite an issued bill
# ═══════════════════════════════════════════════════════════════════════════

def test_a_revision_renumbering_a_line_does_not_change_an_issued_bills_item_numbers(
        client, seeded):
    """
    §4 rule 1 is withdrawn, so a revision may renumber freely — which means a
    bill printed last month against item 17 could re-render as item 18 after a
    revision, silently changing a document already submitted to the main
    contractor. The claim stores the number as it stood and prints that;
    matching is always on line_id.
    """
    li = priced(seeded, 1)[0]
    original = li["item_no"]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    assert STORE["ra_bills"][rid]["claims"][0]["item_no"] == original

    # Revision 1: same line, renumbered.
    rev = dict(STORE["boqs"][seeded])
    rev["id"] = "rev1"
    rev["rev_no"] = 1
    rev["supersedes"] = seeded
    rev["ref"] = "SF/BOQ/26-27/0001-R1"
    rev["line_items"] = [dict(x) for x in STORE["boqs"][seeded]["line_items"]]
    rev["line_items"][STORE["boqs"][seeded]["line_items"].index(li)]["item_no"] = "99.z"
    STORE["boqs"]["rev1"] = rev

    # The stored bill is untouched.
    assert STORE["ra_bills"][rid]["claims"][0]["item_no"] == original

    # And the claim still matches, through the id, against the revision.
    assert ra.claimed_by_line(seeded)[(li["line_id"], "supply")] == 1.0
    assert ra.approved_by_line("rev1")[(li["line_id"], "supply")] == li["total_qty"]

    # The view prints the snapshot, and flags that it has moved.
    h = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert original in h
    assert "now 99.z" in h


# ═══════════════════════════════════════════════════════════════════════════
# THE FORM'S BANDS AND WHAT IS DELIBERATELY ABSENT
# ═══════════════════════════════════════════════════════════════════════════

def test_the_duplicate_item_number_band_is_on_the_ra_form_too(client, seeded):
    """
    The operator sees two rows both labelled 17 in section A and needs the same
    assurance the BOQ form gives — that they are separate items, guarded
    separately, and that entering against either one is unambiguous.
    """
    h = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert "Repeated item number" in h
    assert "separate items here" in h
    assert "cannot touch the other" in h


def test_a_hostile_item_number_cannot_reach_the_error_banner(client, seeded):
    """
    The over-claim message interpolates the item number, and an item number is
    free text somebody types on the BOQ form — so it is a genuine injection
    path into this page's alert. `_alert()` is the choke point that escapes it.
    """
    li = priced(seeded, 1)[0]
    li["item_no"] = "<script>alert(1)</script>"

    h = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-08-06",
        "ra_json": payload([(li["line_id"], li["total_qty"] + 5, 100)])
    }).get_data(as_text=True)

    assert "<script>alert(1)</script>" not in h
    assert "&lt;script&gt;" in h


def test_a_hostile_flash_message_cannot_reach_the_page(client, seeded):
    """?msg= is in the URL, so it is whatever anybody puts there."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])

    h = client.get(f"/ra/view/{rid}?msg=<img src=x onerror=alert(1)>&type=error"
                   ).get_data(as_text=True)
    assert "<img src=x onerror" not in h
    assert "&lt;img" in h


def test_the_deductions_block_is_rendered_and_empty(client, seeded):
    h = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert "Deductions" in h
    assert "No deductions on this bill" in h


def test_certification_is_gone_from_the_module_and_every_page(client, seeded):
    """
    "Remove it ENTIRELY, not behind a flag" (CLIENT_CHANGES.md item 3).

    This is the inversion of `test_no_certification_entry_ui_in_step_2`, which
    asserted the entry UI had not landed *yet*. There is nothing left to land:
    no route, no field, no helper, no column. Asserted against the module's
    public surface AND against the rendered pages, because either alone would
    pass while the other still carried it.
    """
    import app as app_module

    rules = {r.rule for r in app_module.app.url_map.iter_rules()}
    assert not [r for r in rules if "certify" in r]

    assert not [n for n in dir(ra) if "certif" in n.lower()]
    assert "certified" not in ra.STATUSES

    # No claim row is written with a certified pair any more.
    li = priced(seeded, 1)[0]
    assert "certified_qty" not in claim_for(li, 1.0)
    assert "certified_rate" not in claim_for(li, 1.0)

    # Specific tokens, NOT a blanket search for "certif": the client's own
    # seeded schedule contains the sentence "Vendor shall submitt all the
    # Manufacturing and Test certifiates with the delivery of pipes" — their
    # typo, their commercial text, and it must survive untouched (DOMAIN.md §6).
    # A test that greps for the substring would fail on the client's data and
    # invite somebody to "fix" it, which is the exact failure mode that document
    # exists to prevent.
    GONE = ("certified_qty", "certified_rate", "certified_on", "/ra/certify",
            "Certify", "Certification", "Certified")

    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    for url in (f"/ra/create?boq={seeded}&leg=supply", f"/ra/edit/{rid}",
                f"/ra/view/{rid}", f"/ra/print/{rid}", "/ra/"):
        h = client.get(url).get_data(as_text=True)
        for token in GONE:
            assert token not in h, f"{url} still carries {token!r}"


def test_printed_document_route_exists(client, seeded):
    """Step 4 lands printed RA bill tax invoice route /ra/print/<id>."""
    import app as app_module
    rules = {r.rule for r in app_module.app.url_map.iter_rules()}
    assert "/ra/" in rules
    assert "/ra/print/<id>" in rules

    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    h = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "/ra/print/" in h
