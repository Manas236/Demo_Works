"""
Raising a REAL purchase order from a BOQ, and converting a priced draft into one.

Until this shipped there were two purchase-order systems and no path between
them. `po_draft.py` produced a rate-less document (`SF/DPO/nnnn`) sent to a
supplier to be priced; `purchase.py` produced the real order, entered from
scratch, whose only optional upstream link was `quotation_id`. Work raised from
a bill of quantities therefore dead-ended at a draft — and because a real PO
carried no BOQ and no project, **the only record of what procurement actually
cost had no path to the project it was spent on** (ABOUT.md §7).

Two routes close that:

    GET,POST /purchase/from-boq/<boq_id>       tick the lines, price, order
    GET,POST /purchase/from-draft/<draft_id>   the draft comes back priced

What this file holds to, and why each one is here rather than assumed:

1.  the order lands in the **ordinary register** with the ordinary series, and
    nothing about it is a draft or waiting on an approval;
2.  its lines are a **snapshot** — deleting the BOQ line afterwards must not
    move the printed document by a byte. `print_ra()` looped the live BOQ
    instead of the bill's own claims and shipped green for exactly as long as
    every print test rendered against data nobody then touched (ABOUT.md §5);
3.  matching is on **`line_id`** and never on `item_no`. The seeded Sify BOQ has
    87 priced lines and 77 distinct item numbers, and keying on the label waved
    ₹1,99,122.50 of over-claim through on the client's own schedule;
4.  a rate **prefills** from the schedule's supply base rate and an **edit is
    what gets stored**;
5.  the order carries its BOQ and its project, and shows on the project's page;
6.  a **superseded** schedule is refused at the route;
7.  **nothing ticked** is refused, never written as an empty order;
8.  converting a draft carries the supplier, the lines and their ids, and the
    **draft survives**;
9.  converting the same draft **twice** is accepted, with an amber band;
10. ⚠ **a purchase order with no BOQ and no project renders exactly as it did
    before any of this existed.** That is the regression that matters most here,
    and `tests/test_print_golden.py` holds the other half of it byte-for-byte.

⚠ No assertion in this file may pass against a blank page. Every one of them
  names a supplier, a rate, a reference or a link target that only appears when
  the feature actually worked.
"""

import json

import pytest

import address
import boq as BQ
import docsheet as DS
import demo_data as DD
from store import STORE

# A named vendor with a fixed UUID from `address.ensure_demo_addresses()`, so
# every assertion below can name the supplier rather than checking that
# *something* rendered.
VENDOR_ID = "b2000006-face-4000-8000-000000000006"
VENDOR_NAME = "Sanghvi Steel &amp; Pipes"      # as it renders, HTML-escaped
OTHER_VENDOR_ID = "b2000004-face-4000-8000-000000000004"

PROJECT_ID = "proj-boq-to-po"
PROJECT_NAME = "Sify Bangalore Phase II"


@pytest.fixture()
def shop(client):
    """
    A seeded schedule, a named vendor, and a project the BOQ is attached to.

    The demo BOQ carries a fixed UUID and 97 real lines, which is what lets the
    duplicate-`item_no` case below be built from the client's own shape rather
    than invented.
    """
    client.get("/boq/")
    client.get("/settings/")
    address.ensure_demo_addresses()

    bid = DD.BOQ_META["id"]
    STORE.setdefault("projects", {})[PROJECT_ID] = {
        "id": PROJECT_ID, "name": PROJECT_NAME, "norm_name": "sify bangalore phase ii",
        "client": "Prudent Teqtis Pvt Ltd", "site_address": "Bangalore",
        "notes": "", "created_at": "2026-08-16 09:00", "updated_at": "2026-08-16 09:00",
    }
    STORE["boqs"][bid]["project_id"] = PROJECT_ID

    priced = [li for li in STORE["boqs"][bid]["line_items"]
              if not li.get("is_header") and float(li.get("total_qty") or 0) > 0]
    yield {"boq": bid, "lines": priced}

    STORE.setdefault("purchase_orders", {}).clear()
    STORE.setdefault("projects", {}).clear()
    STORE["purchases"].clear()


def _post(client, boq_id, lines, **over):
    """POST `/purchase/from-boq`, with the picker's payload built for us."""
    data = {
        "date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "po_json": json.dumps({"lines": lines}),
    }
    data.update(over)
    return client.post(f"/purchase/from-boq/{boq_id}", data=data)


def _pick(line, qty="", rate=""):
    return {"line_id": line["line_id"], "qty": qty, "rate": rate}


def _only_po():
    assert len(STORE["purchases"]) == 1, "expected exactly one purchase order"
    return next(iter(STORE["purchases"].values()))


# ═══ 1. It lands in the normal register ════════════════════════════════════

def test_a_po_raised_from_a_boq_is_an_ordinary_purchase_order(shop, client):
    """
    **The whole ask.** The operator wants a purchase order, not a workflow: it
    goes straight into `STORE["purchases"]`, takes the ordinary FY-scoped
    `SF/PO/26-27/nnnn` number, and appears on `/purchase/` beside every order
    entered from scratch.

    Specifically it is **not** a second draft. `STORE["purchase_orders"]` is
    `po_draft.py`'s collection and nothing on this path may write to it.
    """
    r = _post(client, shop["boq"], [_pick(shop["lines"][0], qty="5")])
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]

    po = _only_po()
    assert po["ref"] == "SF/PO/26-27/0001"
    assert po["fy"] == "26-27"
    assert not STORE.get("purchase_orders"), (
        "this path wrote a DRAFT purchase order. The operator asked for the "
        "real register — po_draft.py's collection is not it.")

    # No gate of its own. `status` is purchase.py's ordinary lifecycle and was
    # here long before this route; what must not exist is a second one.
    for gate in ("approved", "approval", "pending", "draft_state", "awaiting"):
        assert gate not in po, f"a {gate!r} field appeared — no approval step was asked for"

    html = client.get("/purchase/").get_data(as_text=True)
    assert "SF/PO/26-27/0001" in html
    assert VENDOR_NAME in html, "the register does not name the supplier"
    assert f'href="/purchase/view/{po["id"]}"' in html


# ═══ 2. The lines are a snapshot ═══════════════════════════════════════════

def test_deleting_a_boq_line_afterwards_does_not_move_the_printed_po(shop, client):
    """
    ⚠ **This is `print_ra()`'s defect, guarded one document over.**

    That renderer looped `boq["line_items"]` instead of the bill's own claims, so
    a line dropped from the schedule vanished from the printed table while its
    amount stayed inside the printed subtotal — an invoice whose rows did not add
    up to its own total. The suite was green throughout, because every print test
    rendered a document against a BOQ nobody then touched.

    So this one touches it: it renders the order, deletes a claimed line out of
    the schedule underneath it, and asserts the page is **byte-identical**.
    """
    a, b = shop["lines"][0], shop["lines"][1]
    assert _post(client, shop["boq"], [_pick(a, qty="3"), _pick(b, qty="4")]).status_code == 302
    po = _only_po()

    before = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert po["ref"] in before and VENDOR_NAME in before

    boq = STORE["boqs"][shop["boq"]]
    boq["line_items"] = [li for li in boq["line_items"]
                         if li.get("line_id") != b["line_id"]]
    assert all(li.get("line_id") != b["line_id"] for li in boq["line_items"])

    after = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert after == before, (
        "the printed purchase order moved when a BOQ line was deleted. It is "
        "driven by its own stored rows and must never re-read the live "
        "schedule — ABOUT.md §5, /ra/print reads the RECORD.")


# ═══ 3. line_id is the key; item_no is a label ═════════════════════════════

def test_two_lines_sharing_an_item_no_produce_two_distinct_rows(shop, client):
    """
    The client's own section A carries item **17** twice — a flexible sprinkler
    drop at ₹1,800 and a 150 mm butterfly valve at ₹14,572.50. Keying on
    `item_no` collapsed 87 priced lines into 77 entries and waved ₹1,99,122.50 of
    over-claim through on their real schedule (ABOUT.md §3, property 0).

    Built here to that exact shape: two lines, one item number, two rates.
    """
    boq = STORE["boqs"][shop["boq"]]
    drop = {"line_id": BQ._new_line_id(), "item_no": "17", "parent_item_no": "",
            "section": "A", "is_header": False,
            "description": "Flexible sprinkler drop with braided hose",
            "remark": "", "unit": "Nos", "area_qty": {}, "total_qty": 10.0,
            "supply_base_rate": 1800.0, "supply_escalation_pct": 0.0,
            "supply_rate": 1800.0, "supply_amount": 18000.0,
            "supply_hsn": "84241000", "supply_gst_rate": 18.0,
            "install_base_rate": 400.0, "install_escalation_pct": 0.0,
            "install_rate": 400.0, "install_amount": 4000.0,
            "install_sac": "995461", "install_gst_rate": 18.0}
    valve = dict(drop, line_id=BQ._new_line_id(),
                 description="150 mm dia butterfly valve, wafer type",
                 supply_base_rate=14572.50, supply_rate=14572.50,
                 supply_amount=145725.0, supply_hsn="84818030")
    assert drop["line_id"] != valve["line_id"]
    boq["line_items"] = [drop, valve]

    r = _post(client, shop["boq"],
              [_pick(drop, qty="2"), _pick(valve, qty="3")])
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]

    po = _only_po()
    rows = [r_ for r_ in po["line_items"] if not r_.get("is_header")]
    assert len(rows) == 2, (
        f"two BOQ lines sharing item_no 17 produced {len(rows)} PO row(s). "
        f"Matching collapsed on the display label — it must key on line_id.")

    by_lid = {r_["line_id"]: r_ for r_ in rows}
    assert set(by_lid) == {drop["line_id"], valve["line_id"]}
    assert by_lid[drop["line_id"]]["name"] == drop["description"]
    assert by_lid[valve["line_id"]]["name"] == valve["description"]
    assert by_lid[drop["line_id"]]["price"] == 1800.0
    assert by_lid[valve["line_id"]]["price"] == 14572.50
    # Both still SHOW item 17 — the label is carried, it is just never matched on.
    assert by_lid[drop["line_id"]]["part_no"] == "17"
    assert by_lid[valve["line_id"]]["part_no"] == "17"

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Flexible sprinkler drop with braided hose" in html
    assert "150 mm dia butterfly valve, wafer type" in html
    assert "14,572.50" in html, "the second line's own rate is not on the document"
    assert "1,800.00" in html


# ═══ 4. Rates prefill, and an edit wins ════════════════════════════════════

def test_rates_prefill_from_the_supply_base_rate_and_an_edit_is_what_is_stored(
        shop, client):
    """
    The base rate is what the job was **costed** at, which makes it the right
    opening figure for what we expect to pay — and emphatically not
    `supply_rate`, which is the escalated figure we *sell* at.

    Then the two halves that matter: an **edited** rate is stored rather than the
    prefill, and a box left **blank** falls back to the prefill rather than to
    zero. Blank means "as offered", never "free".
    """
    line = next(li for li in shop["lines"]
                if li.get("supply_base_rate") not in (None, 0))
    other = next(li for li in shop["lines"]
                 if li["line_id"] != line["line_id"]
                 and li.get("supply_base_rate") not in (None, 0))
    base = float(line["supply_base_rate"])

    form = client.get(f"/purchase/from-boq/{shop['boq']}").get_data(as_text=True)
    assert f'id="r_{line["line_id"]}"' in form, "no rate box was rendered for the line"
    assert f'value="{base:.2f}"' in form, (
        f"the rate box did not open at the schedule's supply base rate {base:.2f}")
    assert f'value="{float(line["supply_rate"]):.2f}"' not in form or \
        float(line["supply_rate"]) == base, (
        "the ESCALATED supply rate reached the form. That is what we sell the "
        "work for, not what we expect to pay for the material.")

    r = _post(client, shop["boq"],
              [_pick(line, qty="2", rate="1234.75"), _pick(other, qty="1")])
    assert r.status_code == 302

    po = _only_po()
    by_lid = {r_["line_id"]: r_ for r_ in po["line_items"] if not r_.get("is_header")}
    assert by_lid[line["line_id"]]["price"] == 1234.75, (
        "the typed rate was discarded and the prefill stored instead")
    assert by_lid[line["line_id"]]["total"] == 2469.50
    assert by_lid[other["line_id"]]["price"] == float(other["supply_base_rate"]), (
        "a blank rate box did not fall back to the schedule's base rate")


def test_the_installation_track_never_reaches_a_material_purchase_order(shop, client):
    """
    A BOQ line is priced twice — to supply the material and to install it. The
    installation amount is **labour we perform**, not goods we buy, and putting
    it on an order placed on a vendor would commit us to paying somebody else for
    our own work. `purchase.INCLUDE_INSTALL_TRACK` is where that decision lives.
    """
    import purchase

    assert purchase.INCLUDE_INSTALL_TRACK is False
    assert purchase.RATE_PREFILL_FIELD == "supply_base_rate"

    line = next(li for li in shop["lines"]
                if float(li.get("install_base_rate") or 0) > 0
                and li.get("install_base_rate") != li.get("supply_base_rate"))
    assert _post(client, shop["boq"], [_pick(line, qty="1")]).status_code == 302

    row = next(r_ for r_ in _only_po()["line_items"] if not r_.get("is_header"))
    assert row["price"] == float(line["supply_base_rate"])
    assert row["price"] != float(line["install_base_rate"])
    # The supply HSN comes across; the installation SAC does not.
    assert row["hsn"] == line["supply_hsn"]
    assert row["hsn"] != line["install_sac"]


# ═══ 5. The project link — the gap this whole pass exists to close ═════════

def test_the_po_carries_its_boq_and_project_and_appears_on_the_project_page(
        shop, client):
    """
    **The larger benefit.** Real purchase orders are the only record of actual
    procurement cost, and until now that cost had no path to a project at all.

    `project_id` is inherited from the BOQ at create and then **stored**, not
    derived through `boq_id` — an order entered from scratch can be tagged to a
    project with no schedule behind it, so a lookup would have nothing to look
    through.
    """
    assert _post(client, shop["boq"], [_pick(shop["lines"][0], qty="6")]).status_code == 302
    po = _only_po()

    assert po["boq_id"] == shop["boq"]
    assert po["boq_ref"] == STORE["boqs"][shop["boq"]]["ref"]
    assert po["project_id"] == PROJECT_ID
    assert po["project_name"] == PROJECT_NAME

    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert f'href="/boq/view/{shop["boq"]}"' in view, "the BOQ is not linked on the order"
    assert f'href="/projects/view/{PROJECT_ID}"' in view, "the project is not linked"
    assert po["boq_ref"] in view and PROJECT_NAME in view

    page = client.get(f"/projects/view/{PROJECT_ID}").get_data(as_text=True)
    assert po["ref"] in page, (
        "the order does not appear in the project's purchase orders panel — "
        "procurement cost still has no path to a project.")
    assert f'href="/purchase/view/{po["id"]}"' in page


def test_a_boq_with_no_project_gives_the_order_no_project(shop, client):
    """
    The other half, and it is deliberate rather than a miss. `project_name` on a
    BOQ is a free-text display label; `project_id` is the grouping key. Inventing
    an id-less project from the label would put a row on no project's page while
    looking as though it had one.
    """
    STORE["boqs"][shop["boq"]]["project_id"] = ""
    assert _post(client, shop["boq"], [_pick(shop["lines"][0], qty="1")]).status_code == 302

    po = _only_po()
    assert po["project_id"] == ""
    assert po["project_name"] == ""
    assert PROJECT_NAME not in client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)


# ═══ 6 & 7. The two refusals ═══════════════════════════════════════════════

def test_a_superseded_boq_is_refused_with_a_message(shop, client):
    """
    `/ra/create` and `/dc/create` refuse one for the same reason: a superseded
    revision is not the schedule anybody is building from, so it is not the
    schedule anybody should be buying for. `/boq/view` also hides the link — but
    a link is not a guard, so the route says no as well.
    """
    old = shop["boq"]
    STORE["boqs"]["rev-2"] = dict(STORE["boqs"][old], id="rev-2", rev_no=1,
                                  ref="SF/BOQ/26-27/0002", supersedes=old)
    assert old in BQ.superseded_ids()

    r = client.get(f"/purchase/from-boq/{old}")
    assert r.status_code == 302
    assert f"/boq/view/{old}" in r.headers["Location"]
    assert "superseded" in r.headers["Location"]

    r = _post(client, old, [_pick(shop["lines"][0], qty="1")])
    assert r.status_code == 302 and "superseded" in r.headers["Location"]
    assert not STORE["purchases"], "a superseded schedule still wrote an order"

    # And the control is gone from the action bar, on the same predicate.
    page = client.get(f"/boq/view/{old}").get_data(as_text=True)
    assert f"/purchase/from-boq/{old}" not in page
    assert "/purchase/from-boq/rev-2" in client.get("/boq/view/rev-2").get_data(as_text=True)


def test_nothing_ticked_is_refused_and_writes_nothing(shop, client):
    """
    Refused with a message, never accepted as an empty purchase order. An order
    with no lines on it is not a document, and writing one would burn a number
    from a series a vendor quotes back at us.
    """
    r = _post(client, shop["boq"], [])
    assert r.status_code == 200, "an empty selection was accepted"
    html = r.get_data(as_text=True)
    assert "No lines are ticked" in html
    assert not STORE["purchases"]

    # The form comes back usable rather than as a bare error page.
    assert VENDOR_NAME in html and 'name="po_json"' in html


def test_a_rejected_post_hands_back_the_ticks_and_the_rates(shop, client):
    """
    `address._validate()`'s contract, on a 97-line schedule where losing it
    matters most: a rejected POST re-renders with what was ticked and typed.
    """
    line = shop["lines"][0]
    r = _post(client, shop["boq"], [_pick(line, qty="7", rate="4321.00")],
              vendor_id="")          # refused: no supplier
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Choose the vendor this order goes to." in html
    # The exact two boxes for that exact line, not "a 7 appears somewhere".
    assert (f'id="q_{line["line_id"]}"\n              value="7"') in html, (
        "the ticked quantity was thrown away on rejection")
    assert (f'id="r_{line["line_id"]}"\n              value="4321.00"') in html, (
        "the typed rate was thrown away on rejection")
    assert not STORE["purchases"]


# ═══ 8 & 9. Converting a draft ═════════════════════════════════════════════

def _a_draft(client, boq_id, lines, vendor_id=VENDOR_ID):
    r = client.post(f"/po/create?boq={boq_id}", data={
        "date": "2026-08-16", "vendor_id": vendor_id, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "",
                                          "pcs": ""} for li in lines]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return next(iter(STORE["purchase_orders"]))


def test_converting_a_draft_carries_supplier_lines_and_line_ids(shop, client):
    """
    The return leg ABOUT.md §7 gap B7 named as missing: the priced copy used to
    come back on paper and be re-keyed from scratch, with nothing linking the two
    documents.

    **The draft survives.** It is the record of what was sent out for pricing,
    and deleting it on success would throw away the only evidence of what was
    asked and of whom.
    """
    picked = shop["lines"][:3]
    did = _a_draft(client, shop["boq"], picked)
    draft_ref = STORE["purchase_orders"][did]["ref"]

    form = client.get(f"/purchase/from-draft/{did}").get_data(as_text=True)
    assert f'<option value="{VENDOR_ID}" selected>' in form, (
        "the draft's own supplier did not prefill the picker")
    assert VENDOR_NAME in form

    r = client.post(f"/purchase/from-draft/{did}", data={
        "date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Issued",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "dl_line_id": [li["line_id"] for li in picked],
        "dl_qty": ["2", "3", "4"], "dl_rate": ["", "", ""]})
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]

    po = _only_po()
    assert po["vendor_id"] == VENDOR_ID
    assert po["vendor_name"] == "Sanghvi Steel & Pipes"
    assert po["draft_id"] == did and po["draft_ref"] == draft_ref
    assert po["boq_id"] == shop["boq"]
    assert po["project_id"] == PROJECT_ID

    rows = [r_ for r_ in po["line_items"] if not r_.get("is_header")]
    assert [r_["line_id"] for r_ in rows] == [li["line_id"] for li in picked]
    assert [r_["qty"] for r_ in rows] == [2.0, 3.0, 4.0]
    assert rows[0]["price"] == float(picked[0]["supply_base_rate"]), (
        "a draft carries no rates, so conversion should open at the BOQ's base "
        "rate rather than at zero")

    # The draft is still there, and now points at what it became.
    assert did in STORE["purchase_orders"]
    assert STORE["purchase_orders"][did]["converted_po_ids"] == [po["id"]]

    dv = client.get(f"/po/view/{did}").get_data(as_text=True)
    assert f'href="/purchase/view/{po["id"]}"' in dv
    assert po["ref"] in dv

    reg = client.get("/po/").get_data(as_text=True)
    assert f'href="/purchase/view/{po["id"]}"' in reg, (
        "the draft register has no Converted -> column linking through")


def test_converting_the_same_draft_twice_is_accepted_with_an_amber_band(shop, client):
    """
    **Not blocked.** Two purchase orders off one request for quotation is an
    ordinary thing when an order is split between suppliers or placed in two
    lots. So it warns in the shape of the existing over-claim and party-drift
    bands and lets it through — DOMAIN.md §6: surface it, name it, never
    silently correct it.
    """
    picked = shop["lines"][:2]
    did = _a_draft(client, shop["boq"], picked)
    body = {"date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Draft",
            "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
            "dl_line_id": [li["line_id"] for li in picked],
            "dl_qty": ["1", "1"], "dl_rate": ["100", "200"]}

    assert client.post(f"/purchase/from-draft/{did}", data=body).status_code == 302
    first = next(iter(STORE["purchases"].values()))

    # The band is on the form BEFORE the second conversion, naming the first.
    form = client.get(f"/purchase/from-draft/{did}").get_data(as_text=True)
    assert 'class="up-warn"' in form, "no amber band on a second conversion"
    assert "already been converted" in form
    assert first["ref"] in form and f'href="/purchase/view/{first["id"]}"' in form

    # And it is a warning, not a refusal.
    r = client.post(f"/purchase/from-draft/{did}",
                    data=dict(body, vendor_id=OTHER_VENDOR_ID))
    assert r.status_code == 302, "the second conversion was blocked — it must warn only"

    assert len(STORE["purchases"]) == 2
    refs = sorted(p["ref"] for p in STORE["purchases"].values())
    assert refs == ["SF/PO/26-27/0001", "SF/PO/26-27/0002"]
    assert len(STORE["purchase_orders"][did]["converted_po_ids"]) == 2

    second = next(p for p in STORE["purchases"].values() if p["id"] != first["id"])
    assert second["vendor_name"] == "Vishwakarma Pumps & Motors Pvt. Ltd.", (
        "the split order went to the wrong supplier")


# ═══ 10. The regression that matters most ══════════════════════════════════

def test_a_purchase_order_with_no_boq_and_no_project_renders_exactly_as_before(
        shop, client):
    """
    ⚠ **The one this pass could most easily have broken.**

    Every upstream field is optional and nothing is backfilled, so an order
    entered from scratch — and, harder, one written *before* these fields
    existed — has to render exactly what it always rendered. The strip that
    carries the BOQ, the draft and the project must collapse to nothing at all
    rather than to an empty box or a stray em-dash.

    `tests/test_print_golden.py` holds the byte-for-byte half against a fixed
    record. This holds the behavioural half: a legacy record with **none of the
    keys present**, and a live from-scratch order whose page does not move when a
    BOQ-linked order appears beside it in the store.
    """
    from product import ensure_demo_products
    ensure_demo_products()

    r = client.post("/purchase/create", data={
        "date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "exempt", "line_product_id": [next(iter(STORE["products"]))],
        "line_qty": ["4"], "line_rate": ["750"]})
    assert r.status_code == 302
    scratch = _only_po()
    assert scratch["boq_id"] == "" and scratch["project_id"] == ""
    assert scratch["draft_id"] == ""

    before = client.get(f"/purchase/view/{scratch['id']}").get_data(as_text=True)
    assert VENDOR_NAME in before and "750.00" in before
    assert 'class="po-strip"' not in before, (
        "a from-scratch order drew the upstream strip. It has no upstream.")
    for word in ("&middot; schedule", "&middot; project", "&middot; draft"):
        assert word not in before

    # A BOQ-linked order now exists. The scratch one must not have noticed.
    assert _post(client, shop["boq"], [_pick(shop["lines"][0], qty="2")]).status_code == 302
    assert len(STORE["purchases"]) == 2
    after = client.get(f"/purchase/view/{scratch['id']}").get_data(as_text=True)
    assert after == before, "an unrelated purchase order's page moved"


def test_a_record_written_before_these_fields_existed_still_renders(shop, client):
    """
    The harder half of the same property: not a record with the keys blank, but
    one where **the keys are not there at all**. Nothing backfills them, so this
    is what every purchase order in the client's working database looks like.
    """
    STORE["purchases"]["legacy-po"] = {
        "id": "legacy-po", "ref": "SF/PO/25-26/0042", "fy": "25-26",
        "date": "2026-01-09",
        "vendor_id": "", "vendor_name": "Agnirodh Fire Equipment Co.",
        "vendor_gstin": "27AAECA9012P1Z8",
        "to": "Agnirodh Fire Equipment Co.\nPune", "vendor_ref": "",
        "quotation_id": "", "quotation_ref": "",
        "line_items": [{"type": "item", "name": "Fire extinguisher, 9 kg ABC",
                        "part_no": "FE-9", "hsn": "84241000", "qty": 12.0,
                        "unit": "Nos", "price": 2150.0, "total": 25800.0,
                        "depth": 0}],
        "subtotal": 25800.0, "tax_type": "exempt", "tax_info": {"total": 0.0},
        "grand_total": 25800.0, "total_qty": 12.0,
        "delivery_date": "", "delivery_to": "", "payment_terms": "",
        "delivery_terms": "", "dispatch_through": "", "incoterms": "",
        "status": "Received", "status_history": [], "notes": "",
        "company_branch": "", "auth_signatory": "",
    }
    for absent in ("boq_id", "project_id", "draft_id", "project_name"):
        assert absent not in STORE["purchases"]["legacy-po"]

    r = client.get("/purchase/view/legacy-po")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "SF/PO/25-26/0042" in html
    assert "Agnirodh Fire Equipment Co." in html
    assert "2,150.00" in html and "25,800.00" in html
    assert 'class="po-strip"' not in html
    # And it is still in the register, untouched.
    assert "SF/PO/25-26/0042" in client.get("/purchase/").get_data(as_text=True)


# ═══ The document itself ═══════════════════════════════════════════════════

def test_the_specification_header_comes_across_and_carries_no_money(shop, client):
    """
    A ticked size brings its specification clause with it, so the supplier can
    read what they are being asked to supply (DOMAIN.md §2.2). It carries no
    quantity, no rate and no amount, takes no serial number, and is counted in
    neither total.
    """
    boq = STORE["boqs"][shop["boq"]]
    child = next(li for li in boq["line_items"]
                 if not li.get("is_header") and li.get("parent_item_no"))
    header = next(li for li in boq["line_items"]
                  if li.get("is_header")
                  and BQ._item_no(li.get("item_no")) == BQ._item_no(child["parent_item_no"])
                  and li.get("section") == child.get("section"))

    assert _post(client, shop["boq"], [_pick(child, qty="2", rate="1000")]).status_code == 302
    po = _only_po()

    heads = [r_ for r_ in po["line_items"] if r_.get("is_header")]
    assert len(heads) == 1
    assert heads[0]["part_no"] == BQ._item_no(header["item_no"])
    assert heads[0]["qty"] == 0.0 and heads[0]["price"] == 0.0 and heads[0]["total"] == 0.0
    assert po["subtotal"] == 2000.0, "the header row leaked into the order value"
    assert po["total_qty"] == 2.0, "the header row leaked into the quantity total"

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert 'class="row-assembly"' in html
    # Was `colspan="6"` until 27 Aug 2026, when A2's discount column took the
    # buy sheet from eight columns to nine (`DS.BUY_COLUMNS`). The header row
    # still spans every column after S.No and Part No, which is what this
    # asserts; the literal is the table's width and tracks it.
    assert 'colspan="7"' in html
    assert len(DS.BUY_COLUMNS) == 9, "the span above is 9 - 2 and must follow it"
    # And it is still a header: no quantity, no rate, no amount in the row.
    row = html.split('class="row-assembly"', 1)[1].split("</tr>", 1)[0]
    assert 'class="c-qty"' not in row and 'class="c-total"' not in row


def test_the_order_value_is_the_ordinary_input_tax_arithmetic(shop, client):
    """
    Nothing about the tax changed and nothing about it may. This is **input** tax
    we pay, the opposite side of the ledger from a tax invoice, computed by the
    same `quotation._tax_lines()` every purchase order has always used with SGST
    forced equal to CGST.
    """
    line = shop["lines"][0]
    r = _post(client, shop["boq"], [_pick(line, qty="10", rate="1000")],
              tax_type="cgst_sgst", cgst_rate="9")
    assert r.status_code == 302

    po = _only_po()
    assert po["subtotal"] == 10000.0
    assert po["tax_info"]["CGST"] == 900.0
    assert po["tax_info"]["SGST"] == 900.0
    assert po["grand_total"] == 11800.0

    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "11,800.00" in html
