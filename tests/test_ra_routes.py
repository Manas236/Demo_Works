"""
Phase 4 step 2 — the RA entry form.

The routes that make an RA bill enterable: the blueprint, the create form, the
edit route gated to the latest bill, and the POST-only delete. Plus the record
shape and arithmetic for certification, whose entry UI is step 3.

Three properties everything here circles:

- **The block is hard, and it is CUMULATIVE.** Per-bill would pass nine times
  and still end 9% over.
- **The claim freezes; the certificate never does.** Two edit permissions on
  one record, because RA3 comes back certified after RA6 has been raised.
- **Uncertified is not zero.** A blank certified field means "not yet ruled
  on", and summing it as zero under-reports what is owed.
"""

import json

import pytest

import boq as BQ
import demo_data as DD
import ra
from store import STORE


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(client):
    """The real 97-line Sify BOQ, seeded through the app."""
    STORE["ra_bills"].clear()
    BQ.ensure_demo_boq()
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
        "status": "draft", "certified_on": "", "notes": "",
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
# MUTABILITY — the claim freezes, the certificate never does
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
    assert "certification can still be recorded" in why


# ═══════════════════════════════════════════════════════════════════════════
# CERTIFICATION — record, arithmetic and rules. The UI is step 3.
# ═══════════════════════════════════════════════════════════════════════════

def test_a_new_claim_row_starts_uncertified_not_zero(seeded):
    li = priced(seeded, 1)[0]
    c = claim_for(li, 5.0)
    assert c["certified_qty"] is None
    assert c["certified_rate"] is None
    assert ra.is_certified(c) is False
    assert ra.certified_amount(c) is None


def test_a_blank_certified_field_is_never_summed_as_zero(seeded):
    """
    THE receivables error, inverted. Summing an unanswered line as zero
    under-reports what is owed — the exact opposite of what this system was
    sold to catch.
    """
    lines = priced(seeded, 3)
    claims = [claim_for(li, 2.0, rate=100.0) for li in lines]
    claims[0]["certified_qty"] = 2.0
    claims[0]["certified_rate"] = 100.0
    rid = make_bill(seeded, 1, claims=claims)

    s = ra.certification_summary(STORE["ra_bills"][rid])
    assert s["certified"] == 1 and s["total"] == 3
    assert s["complete"] is False
    assert s["amount"] == 200.0          # ONLY the certified line


def test_a_certified_quantity_of_zero_is_a_ruling_and_counts(seeded):
    """0 certified is the contractor saying "I allow nothing" — an answer.
    Blank is the absence of one. The two must not collapse."""
    li = priced(seeded, 1)[0]
    c = claim_for(li, 5.0)
    c["certified_qty"] = 0.0
    assert ra.is_certified(c) is True
    assert ra.certified_amount(c) == 0.0


def test_certified_above_claimed_warns_and_does_not_block(seeded):
    li = priced(seeded, 1)[0]
    c = claim_for(li, 5.0, rate=100.0)
    c["certified_qty"] = 7.0

    warns = ra.certification_warnings([c])
    assert len(warns) == 1
    assert warns[0]["claimed"] == 5.0 and warns[0]["certified"] == 7.0
    assert "more than was asked for" in ra.certification_warning_message(warns[0])


def test_the_overclaim_block_never_reads_a_certified_field(seeded):
    """
    You cannot claim beyond the BOQ; what the contractor then certifies is his
    decision, not a validation input. Certifying far above the approved
    quantity must not make a within-quantity claim fail, nor rescue an
    over-claim.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    c = claim_for(li, li["total_qty"])
    c["certified_qty"] = li["total_qty"] * 10
    make_bill(seeded, 1, claims=[c])

    # Within quantity, wildly over-certified: still no breach from the certificate.
    assert ra.overclaims(seeded, "supply", [], exclude_ra_id="r1-supply") == []

    # And one more unit is still refused, on CLAIMED quantity.
    fresh = claim_for(li, 1.0)
    breaches = ra.overclaims(seeded, "supply", [fresh])
    assert len(breaches) == 1
    assert breaches[0]["previously"] == li["total_qty"]


def test_certification_is_editable_on_a_frozen_bill(seeded):
    """
    The critical interaction. Certification lags in the real world — RA3 comes
    back certified after RA6 has been raised — so freezing the certificate with
    the claim would make the field unusable exactly when it is needed.
    """
    lines = priced(seeded, 2)
    first = make_bill(seeded, 1, claims=[claim_for(lines[0], 2.0, rate=100.0)])
    make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])

    bill = STORE["ra_bills"][first]
    assert ra.claim_is_frozen(bill) is True       # claim is shut

    lid = bill["claims"][0]["line_id"]
    ra.apply_certification(bill, {lid: {"certified_qty": 1.5,
                                        "certified_rate": 90.0}},
                           status="certified", certified_on="2026-09-01")

    assert bill["claims"][0]["certified_qty"] == 1.5
    assert bill["status"] == "certified"
    assert bill["certified_on"] == "2026-09-01"


def test_certifying_a_frozen_bill_does_not_reopen_its_claim(seeded):
    """The two permissions stay separate: writing a certificate must not make
    the claim editable again, nor alter a single claimed figure."""
    lines = priced(seeded, 2)
    first = make_bill(seeded, 1, claims=[claim_for(lines[0], 2.0, rate=100.0)])
    make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])

    bill = STORE["ra_bills"][first]
    before = {k: bill["claims"][0][k] for k in ("qty", "rate", "amount",
                                                "approved_qty", "balance_qty")}
    lid = bill["claims"][0]["line_id"]
    ra.apply_certification(bill, {lid: {"certified_qty": 99.0}})

    assert ra.claim_is_frozen(bill) is True       # STILL frozen
    for k, v in before.items():
        assert bill["claims"][0][k] == v, f"certifying rewrote {k}"


def test_certified_totals_are_reported_as_n_of_m_bills(seeded):
    lines = priced(seeded, 2)
    done = claim_for(lines[0], 1.0, rate=100.0)
    done["certified_qty"] = 1.0
    make_bill(seeded, 1, claims=[done])
    make_bill(seeded, 2, claims=[claim_for(lines[1], 1.0)])

    assert ra.bills_certified(seeded) == (1, 2)


# ═══════════════════════════════════════════════════════════════════════════
# DELETE — latest only, POST only, never a certified bill
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


def test_a_bill_carrying_certification_is_never_deleted(client, seeded):
    """
    It has been out of the building and acknowledged by the main contractor;
    deleting it destroys the only record of what was allowed against what was
    claimed.
    """
    li = priced(seeded, 1)[0]
    c = claim_for(li, 2.0, rate=100.0)
    c["certified_qty"] = 1.5
    rid = make_bill(seeded, 1, claims=[c])

    allowed, why = ra.can_delete(STORE["ra_bills"][rid])
    assert allowed is False
    assert "certification" in why.lower()

    client.post(f"/ra/delete/{rid}")
    assert rid in STORE["ra_bills"]


def test_the_delete_refusal_is_shown_not_hidden(client, seeded):
    """Refuse with a message saying why; a control that vanishes teaches
    nothing about why."""
    li = priced(seeded, 1)[0]
    c = claim_for(li, 2.0, rate=100.0)
    c["certified_qty"] = 1.5
    rid = make_bill(seeded, 1, claims=[c])

    h = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "Delete" in h                            # the button is still there
    assert "cannot be deleted" in h                 # with the reason on it


def test_a_status_of_certified_alone_blocks_the_delete(seeded):
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)], status="certified")
    assert ra.has_certification(STORE["ra_bills"][rid]) is True
    assert ra.can_delete(STORE["ra_bills"][rid])[0] is False


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


def test_no_certification_entry_ui_in_step_2(client, seeded):
    """The record shape, the arithmetic and the tests are step 2. The entry UI
    is step 3, on the register."""
    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    for url in (f"/ra/create?boq={seeded}&leg=supply", f"/ra/edit/{rid}"):
        h = client.get(url).get_data(as_text=True)
        assert 'name="certified_qty"' not in h
        assert 'id="certified_qty"' not in h


def test_no_printed_document_and_no_register_listing(client, seeded):
    """Steps 3 and 4. The view page is a working screen, not the A4 sheet."""
    import app as app_module
    rules = {r.rule for r in app_module.app.url_map.iter_rules()}
    assert "/ra/" not in rules                   # no register listing
    assert "/ra/print/<id>" not in rules

    li = priced(seeded, 1)[0]
    rid = make_bill(seeded, 1, claims=[claim_for(li, 1.0)])
    h = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "printed RA bill is a later step" in h
