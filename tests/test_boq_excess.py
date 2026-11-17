"""
BILLING ABOVE THE BOQ QUANTITY — allowed, never silent
(17 November 2026, CLIENT_CHANGES.md §0 eighty-first block, prod hotfix 6).

What this file holds:

  * an RA claim whose CUMULATIVE quantity passes the BOQ quantity is refused
    without a reason, with an amber per-line warning (BOQ qty, already claimed,
    this claim, excess) and the ONE reason box; with a reason it is SAVED;
  * the bill stores `excess_lines` (line_id, boq_qty, cumulative_after,
    excess) and `excess_reason`, snapshotted at save and never recomputed;
    a bill within its schedule carries neither key;
  * the cumulative is derived by summing and keyed on `line_id`;
  * the band is drawn on the RA, merged RA, TI and BOQ view pages, screen only;
    the PRINT is unchanged;
  * the measurement cap, a line not in the schedule and the dispatched cap are
    still hard blocks, reason or none;
  * the merged set (`/raboth/create`) and the tax invoice raised from a BOQ.
"""

import json
import re

import pytest

import boq as BQ
import boqexcess as BX
import demo_data as DD
import ra
from store import STORE

from conftest import chain_ready

REASON = "Site measurement exceeds the BOQ; joint record signed 14 Nov."


@pytest.fixture()
def sched(client):
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()
    client.get("/boq/")
    client.get("/settings/")
    bid = DD.BOQ_META["id"]
    yield bid
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()


@pytest.fixture()
def seeded(sched):
    chain_ready(sched)
    yield sched


def _line(bid, min_qty=2):
    return next(li for li in STORE["boqs"][bid]["line_items"]
                if not li["is_header"] and li["total_qty"] >= min_qty
                and float(li.get("supply_rate") or 0) > 0)


def _ra_json(*rows):
    return json.dumps({"lines": [{"line_id": li["line_id"], "qty": str(q),
                                  "rate": str(li["supply_rate"])} for li, q in rows]})


def _raise(client, bid, rows, **extra):
    data = {"date": "2026-11-17", "ra_json": _ra_json(*rows)}
    data.update(extra)
    return client.post(f"/ra/create?boq={bid}&leg=supply", data=data)


def _only_bill():
    [b] = STORE["ra_bills"].values()
    return b


# ── RA, single ──────────────────────────────────────────────────────────────

def test_above_boq_without_a_reason_is_refused_with_the_amber_warning(client, seeded):
    li = _line(seeded)
    r = _raise(client, seeded, [(li, li["total_qty"] + 3)])
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and STORE["ra_bills"] == {}, "nothing saved"
    assert "would be billed above the BOQ quantity" in h
    assert 'class="boq-excess-warn' in h and f'name="{BX.REASON_FIELD}"' in h
    warn = h.split('class="boq-excess-warn', 1)[1].split("</div>", 1)[0]
    for col in ("BOQ qty", "Already claimed", "This claim", "Excess"):
        assert col in warn
    assert f"<b>3</b>" in warn, "the excess, 3 over"
    # The arithmetic the old block carried is still said, word for word.
    assert f'Item {li["item_no"]}' in h and "approved" in h and "over" in h


def test_a_whitespace_reason_is_a_blank_reason(client, seeded):
    li = _line(seeded)
    _raise(client, seeded, [(li, li["total_qty"] + 1)], **{BX.REASON_FIELD: "   "})
    assert STORE["ra_bills"] == {}


def test_above_boq_with_a_reason_is_saved_with_its_snapshot(client, seeded):
    li = _line(seeded)
    q = li["total_qty"]
    r = _raise(client, seeded, [(li, q + 3)], **{BX.REASON_FIELD: REASON})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    bill = _only_bill()
    assert bill[BX.REASON_KEY] == REASON
    [row] = bill[BX.LINES_KEY]
    assert row["line_id"] == li["line_id"] and row["leg"] == "supply"
    assert row["boq_qty"] == q
    assert row["cumulative_after"] == q + 3 and row["excess"] == 3
    assert [c["qty"] for c in bill["claims"]] == [q + 3], "the claim is what was typed"


def test_a_bill_within_its_boq_carries_no_new_key(client, seeded):
    li = _line(seeded)
    _raise(client, seeded, [(li, li["total_qty"])], **{BX.REASON_FIELD: REASON})
    bill = _only_bill()
    assert BX.LINES_KEY not in bill and BX.REASON_KEY not in bill


def test_the_cumulative_is_summed_across_bills(client, seeded):
    li = _line(seeded, min_qty=4)
    q = li["total_qty"]
    # The first bill is within the schedule.
    assert _raise(client, seeded, [(li, q - 1)]).status_code == 302
    first = _only_bill()
    first["status"] = "issued"
    # The second, alone within it, passes it cumulatively: 2 above.
    r = _raise(client, seeded, [(li, 3)])
    assert r.status_code == 200 and len(STORE["ra_bills"]) == 1
    assert _raise(client, seeded, [(li, 3)], **{BX.REASON_FIELD: REASON}).status_code == 302
    second = next(b for b in STORE["ra_bills"].values() if b is not first)
    [row] = second[BX.LINES_KEY]
    assert row["cumulative_after"] == q + 2 and row["excess"] == 2
    assert BX.LINES_KEY not in first


def test_the_two_item_17s_are_told_apart_by_line_id(client, seeded):
    """One item number, two lines: excess on the valve never names the drop."""
    both = [li for li in STORE["boqs"][seeded]["line_items"]
            if li["section"] == "A" and li["item_no"] == "17" and not li["is_header"]]
    valve = next(li for li in both if li["supply_rate"] == 14572.5)
    drop = next(li for li in both if li["supply_rate"] == 1800.0)
    r = _raise(client, seeded, [(valve, 2), (drop, 1)], **{BX.REASON_FIELD: REASON})
    assert r.status_code == 302
    [row] = _only_bill()[BX.LINES_KEY]
    assert row["line_id"] == valve["line_id"] != drop["line_id"]


def test_the_snapshot_is_never_recomputed(client, seeded):
    li = _line(seeded)
    q = li["total_qty"]
    _raise(client, seeded, [(li, q + 3)], **{BX.REASON_FIELD: REASON})
    bill = _only_bill()
    li["total_qty"] = q + 10           # the schedule moves after the save
    try:
        assert bill[BX.LINES_KEY][0]["boq_qty"] == q
        view = client.get(f"/ra/view/{bill['id']}").get_data(as_text=True)
        assert "3 above" in view, "the band reads the stored snapshot"
    finally:
        li["total_qty"] = q


def test_the_ra_band_is_screen_only_and_the_print_is_unchanged(client, seeded):
    li = _line(seeded)
    _raise(client, seeded, [(li, li["total_qty"] + 3)], **{BX.REASON_FIELD: REASON})
    bill = _only_bill()
    # The RA view is a screen page; `/ra/print` is the sheet.
    view = client.get(f"/ra/view/{bill['id']}").get_data(as_text=True)
    assert "Billed above BOQ" in view and REASON in view
    assert 'class="boq-excess-band no-print"' in view
    pr =client.get(f"/ra/print/{bill['id']}").get_data(as_text=True)
    assert "Billed above BOQ" not in pr and REASON not in pr
    # Byte-identical print with and without the snapshot.
    lines, why = bill.pop(BX.LINES_KEY), bill.pop(BX.REASON_KEY)
    bare = client.get(f"/ra/print/{bill['id']}").get_data(as_text=True)
    bill[BX.LINES_KEY], bill[BX.REASON_KEY] = lines, why
    assert client.get(f"/ra/print/{bill['id']}").get_data(as_text=True) == bare
    assert BX.band_html({}) == "" and BX.boq_band_html(set()) == ""


def test_a_draft_edit_reopens_with_its_reason_and_drops_the_keys_within_boq(client, seeded):
    li = _line(seeded)
    q = li["total_qty"]
    _raise(client, seeded, [(li, q + 3)], **{BX.REASON_FIELD: REASON})
    bill = _only_bill()
    form = client.get(f"/ra/edit/{bill['id']}").get_data(as_text=True)
    assert 'class="boq-excess-warn' in form and REASON in form
    # Edited, still above, reason cleared: refused.
    r = client.post(f"/ra/edit/{bill['id']}", data={
        "date": "2026-11-17", "ra_json": _ra_json((li, q + 4)), BX.REASON_FIELD: ""})
    assert r.status_code == 200 and bill["claims"][0]["qty"] == q + 3
    # Edited back within the schedule: both keys go.
    r = client.post(f"/ra/edit/{bill['id']}", data={
        "date": "2026-11-17", "ra_json": _ra_json((li, q))})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert BX.LINES_KEY not in bill and BX.REASON_KEY not in bill


def test_the_hard_blocks_stay_hard_with_a_reason(seeded):
    boq = STORE["boqs"][seeded]
    li = _line(seeded)
    # Not in the schedule.
    raw = json.dumps({"lines": [{"line_id": "ffffffffffff", "qty": "1", "rate": "1"}]})
    claims, _r, err = ra._validate(raw, boq, "supply", {}, excess_reason=REASON)
    assert claims == [] and err
    # The dispatched cap (RA from challans).
    raw = _ra_json((li, 2))
    claims, _r, err = ra._validate(raw, boq, "supply", {},
                                   dc_caps={li["line_id"]: 1.0}, excess_reason=REASON)
    assert claims == [] and err
    # The measurement cap: a sheet on the chain caps installation, reason or none.
    import measurement as MS
    lid = li["line_id"]
    orig = MS.approved_qty_by_line
    MS.approved_qty_by_line = lambda *_a, **_k: {lid: 1.0}
    try:
        breaches = ra.overclaims(seeded, "installation", [{"line_id": lid, "qty": 2}])
        assert breaches and breaches[0]["reason"] == "overmeasured"
        out = []
        ok, _r, err = ra._validate(json.dumps({"lines": [{"line_id": lid, "qty": "2",
                                                          "rate": str(li.get("install_rate") or 1)}]}),
                                   boq, "installation", {}, excess_reason=REASON,
                                   excess_out=out)
        assert ok == [] and err and out == []
    finally:
        MS.approved_qty_by_line = orig


def test_the_boq_view_lists_the_bills_billed_above_it(client, seeded):
    li = _line(seeded)
    page = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "Billed above BOQ" not in page
    _raise(client, seeded, [(li, li["total_qty"] + 3)], **{BX.REASON_FIELD: REASON})
    page = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "Billed above BOQ" in page and REASON in page
    pr = client.get(f"/boq/print/{seeded}").get_data(as_text=True)
    assert "Billed above BOQ" not in pr


# ── The merged set (/raboth/create) ─────────────────────────────────────────

def _both_boxes(html, leg):
    flat = " ".join(html.split())
    return re.findall(
        r'name="%s_qty_([0-9a-f]{12})"[^>]*?/>.*?name="%s_rate_\1" value="([^"]*)"'
        % (leg, leg), flat)


def _both(client, bid, extra=None):
    html = client.get(f"/raboth/create?boq={bid}").get_data(as_text=True)
    data = {"boq": bid, "date": "2026-11-17"}
    (slid, srate), = _both_boxes(html, "supply")[:1]
    (ilid, irate), = _both_boxes(html, "installation")[:1]
    sq = next(li for li in STORE["boqs"][bid]["line_items"]
              if li.get("line_id") == slid)["total_qty"]
    data.update({f"supply_qty_{slid}": str(sq + 2), f"supply_rate_{slid}": srate,
                 f"installation_qty_{ilid}": "1", f"installation_rate_{ilid}": irate})
    data.update(extra or {})
    return client.post(f"/raboth/create?boq={bid}", data=data), slid


def test_the_merged_set_needs_a_reason_and_saves_with_one(client, sched):
    r, slid = _both(client, sched)
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and STORE["ra_bills"] == {} and STORE["merged_ras"] == {}
    assert 'class="boq-excess-warn' in h
    r, slid = _both(client, sched, {BX.REASON_FIELD: REASON})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    sup = next(b for b in STORE["ra_bills"].values() if b["leg"] == "supply")
    ins = next(b for b in STORE["ra_bills"].values() if b["leg"] == "installation")
    assert sup[BX.LINES_KEY][0]["line_id"] == slid and sup[BX.LINES_KEY][0]["excess"] == 2
    assert sup[BX.REASON_KEY] == REASON
    assert BX.LINES_KEY not in ins, "the leg within its schedule carries no key"
    [mg] = STORE["merged_ras"].values()
    assert BX.LINES_KEY not in mg, "the merged record holds no claims, so no excess"
    view = client.get(f"/merged/view/{mg['id']}").get_data(as_text=True)
    assert "Billed above BOQ" in view and REASON in view
    pr = client.get(f"/merged/print/{mg['id']}").get_data(as_text=True)
    assert "Billed above BOQ" not in pr and REASON not in pr


# ── The tax invoice raised from a BOQ ───────────────────────────────────────

def _ti(client, bid, li, qty, **extra):
    form = {"date": "2026-11-17", "place_of_supply": "Karnataka",
            "advance_received": "0", "leg": "supply", "tax_type": "cgst_sgst",
            "ti_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": str(qty)}]})}
    form.update(extra)
    return client.post(f"/invoice/from-boq/{bid}", data=form)


def test_the_boq_tax_invoice_warns_needs_a_reason_and_snapshots(client, sched):
    li = _line(sched)
    q = li["total_qty"]
    before = set(STORE["invoices"])
    r = _ti(client, sched, li, q + 2)
    assert r.status_code == 200 and set(STORE["invoices"]) == before
    assert 'class="boq-excess-warn' in r.get_data(as_text=True)
    r = _ti(client, sched, li, q + 2, **{BX.REASON_FIELD: REASON})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    [iid] = set(STORE["invoices"]) - before
    ti = STORE["invoices"][iid]
    [row] = ti[BX.LINES_KEY]
    assert (row["line_id"], row["boq_qty"], row["cumulative_after"], row["excess"]) == \
        (li["line_id"], q, q + 2, 2)
    view = client.get(f"/invoice/view/{iid}").get_data(as_text=True)
    screen, sheet = view.split('class="doc-outer"', 1)
    assert "Billed above BOQ" in screen and "Billed above BOQ" not in sheet
    # The print is unchanged by the snapshot.
    lines, why = ti.pop(BX.LINES_KEY), ti.pop(BX.REASON_KEY)
    bare = client.get(f"/invoice/view/{iid}").get_data(as_text=True).split('class="doc-outer"', 1)[1]
    ti[BX.LINES_KEY], ti[BX.REASON_KEY] = lines, why
    assert sheet == bare
    page = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert f"Tax invoice {ti['ref']}" in page


def test_boq_tax_invoices_are_cumulative_and_a_cancelled_one_does_not_count(client, sched):
    li = _line(sched, min_qty=2)
    q = li["total_qty"]
    before = set(STORE["invoices"])
    assert _ti(client, sched, li, q).status_code == 302          # within it
    [first] = set(STORE["invoices"]) - before
    assert BX.LINES_KEY not in STORE["invoices"][first]
    assert _ti(client, sched, li, 1).status_code == 200          # 1 above, cumulatively
    STORE["invoices"][first]["status"] = "cancelled"
    assert _ti(client, sched, li, 1).status_code == 302          # nothing live before it


def test_a_ti_within_the_boq_carries_no_new_key(client, sched):
    li = _line(sched)
    before = set(STORE["invoices"])
    assert _ti(client, sched, li, li["total_qty"]).status_code == 302
    [iid] = set(STORE["invoices"]) - before
    ti = STORE["invoices"][iid]
    assert BX.LINES_KEY not in ti and BX.REASON_KEY not in ti
