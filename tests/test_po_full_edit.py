"""
The Product Inquiry (draft PO) is fully editable until it is converted —
29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, A2.

    every field and every line is editable while the Draft PO is unconverted.
    Locked once converted to a real PO: refuse on POST as well as hiding the
    form.

The second sentence is the one that needs a test: a form that is merely not
drawn is not a lock. Every assertion below either names a value that only
appears when the editor worked, or hits the POST directly with the form the
GET refuses to draw.

⚠ **There is NO RATE BOX, and that is A2's one recorded conflict with its own
  brief** (the §0 block names it). `po_draft.PRINT_RATES` is False, the module
  docstring says nothing on this document may read a buy rate from anywhere,
  and B1 renames it *Product Inquiry* — an inquiry asks the supplier for
  rates. Pinned below so a later pass has to take the decision again rather
  than drift into it.
"""

import json

import pytest

import boq as BQ
import po_draft as PD
import settings as SET
from store import STORE

VENDOR_ID = "b2000003-face-4000-8000-000000000003"


@pytest.fixture()
def shop(client):
    """A small BOQ, a vendor, and a clean draft-PO collection and series."""
    import address
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    STORE.setdefault("purchases", {}).clear()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    bid = next(b for b, rec in STORE["boqs"].items() if not rec.get("supersedes"))
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    lines = [li for li in STORE["boqs"][bid]["line_items"]
             if not li.get("is_header")][:2]
    yield {"boq": bid, "vendor": vendor, "lines": lines}
    STORE["purchase_orders"].clear()
    STORE["purchases"].clear()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)


def _a_draft(client, shop):
    payload = json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                     "pcs": "2"} for li in shop["lines"]]})
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "terms here",
        "delivery_to": "Site store", "po_json": payload})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return next(iter(STORE["purchase_orders"].values()))


def _rows(po, over=None, add=(), drop=frozenset()):
    """
    The whole repeater as the editor posts it, with per-row overrides.

    `over` is `{index: {field: value}}`, keyed by the row's position in
    `items`; `add` is a list of rows appended; `drop` is the set of indices
    left out entirely. A dict rather than `**kwargs` because the keys are
    integers.
    """
    over = dict(over or {})
    body = {"date": "2026-10-29", "vendor_id": VENDOR_ID,
            "notes": "terms here", "delivery_to": "Site store",
            # The marker that says the editor was drawn — without it the POST
            # is a stale tab and the lines are left alone (`parse_items()`).
            "it_rows": "1",
            "it_line_id": [], "it_kind": [], "it_item_no": [], "it_desc": [],
            "it_unit": [], "it_qty": [], "it_pcs": [], "it_make": [],
            "it_hsn": [], "it_image": []}

    def _push(row, head):
        body["it_line_id"].append(row.get("line_id") or "")
        body["it_kind"].append("header" if head else "item")
        body["it_item_no"].append(str(row.get("item_no") or ""))
        body["it_desc"].append(str(row.get("description") or ""))
        body["it_unit"].append("" if head else str(row.get("unit") or ""))
        body["it_qty"].append("" if head else str(row.get("qty") or ""))
        body["it_pcs"].append("" if head else str(row.get("pcs") or ""))
        body["it_make"].append("" if head else str(row.get("make") or ""))
        body["it_hsn"].append("" if head else str(row.get("hsn") or ""))
        body["it_image"].append(str(row.get("image") or ""))

    for i, row in enumerate(po.get("items") or []):
        if i in drop:
            continue
        row = dict(row)
        row.update(over.get(i, {}))
        _push(row, bool(row.get("is_header")))
    for row in add:
        _push(row, bool(row.get("is_header")))
    return body


# ═══ 1. Everything on a line is editable while unconverted ═════════════════

def test_the_edit_form_draws_a_box_for_every_field_on_every_line(client, shop):
    d = _a_draft(client, shop)
    page = client.get(f"/po/edit/{d['id']}").get_data(as_text=True)
    n_items = sum(1 for r in d["items"] if not r.get("is_header"))
    for name in ("it_item_no", "it_desc", "it_unit", "it_qty", "it_pcs",
                 "it_make", "it_hsn"):
        assert f'name="{name}"' in page, name
    assert page.count('name="it_kind"') == len(d["items"])
    assert page.count('name="it_line_id"') == len(d["items"])
    assert page.count('name="it_image"') == len(d["items"])
    assert n_items >= 1
    assert "edAdd(false)" in page and "edAdd(true)" in page
    assert "edDel(this)" in page
    # And the vendor, the dates and the terms, which were already here.
    for name in ("vendor_id", "vendor_name", "vendor_gstin", "vendor_addr",
                 "date", "delivery_to", "notes"):
        assert f'name="{name}"' in page, name


def test_every_field_on_a_line_round_trips(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {
        "item_no": "99.b", "description": "Gate valve 200 NB, flanged",
        "unit": "Set", "qty": "12.5", "pcs": "7", "make": "Kirloskar",
        "hsn": "84818030"}}))
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    row = d["items"][n]
    assert row["item_no"] == "99.b"
    assert row["description"] == "Gate valve 200 NB, flanged"
    assert row["unit"] == "Set" and row["qty"] == 12.5
    assert row["pcs"] == "7" and row["make"] == "Kirloskar"
    assert row["hsn"] == "84818030"
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert "Gate valve 200 NB, flanged" in html
    assert '<td class="c-make">Kirloskar</td>' in html
    assert '<td class="c-qty">12.5</td>' in html
    assert '<td class="c-pcs">7</td>' in html


def test_a_blank_make_or_hsn_removes_the_key_rather_than_storing_empty(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    client.post(f"/po/edit/{d['id']}",
                data=_rows(d, {n: {"make": "SANT", "hsn": "73072900"}}))
    assert d["items"][n]["make"] == "SANT" and d["items"][n]["hsn"] == "73072900"
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"make": "", "hsn": ""}}))
    assert "make" not in d["items"][n] and "hsn" not in d["items"][n]


# ═══ 2. Lines are added and removed ════════════════════════════════════════

def test_a_line_is_added(client, shop):
    d = _a_draft(client, shop)
    was = len(d["items"])
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, add=[
        {"description": "Pressure gauge, 0-16 bar", "unit": "Nos",
         "qty": "3", "make": "H Guru", "hsn": "90262000"}]))
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    assert len(d["items"]) == was + 1
    added = d["items"][-1]
    assert added["description"] == "Pressure gauge, 0-16 bar"
    assert added["qty"] == 3.0 and added["make"] == "H Guru"
    assert BQ._line_id(added["line_id"]) == added["line_id"], (
        "a hand-added line must carry a MINTED line_id — the Pictures page "
        "and purchase.from_draft() both address a row by it")
    assert added["line_id"] not in {r["line_id"] for r in d["items"][:-1]}
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert "Pressure gauge, 0-16 bar" in html


def test_a_hand_added_line_is_on_no_boq_and_still_converts(client, shop):
    """
    This document is a request for a supplier's prices, not a claim measured
    against a schedule. Nothing about a draft PO is capped by the BOQ.
    """
    d = _a_draft(client, shop)
    client.post(f"/po/edit/{d['id']}", data=_rows(d, add=[
        {"description": "Something not on the schedule", "unit": "Nos",
         "qty": "1", "hsn": "73072900"}]))
    added = d["items"][-1]
    boq_ids = {BQ._line_id(li.get("line_id"))
               for li in STORE["boqs"][shop["boq"]]["line_items"]}
    assert added["line_id"] not in boq_ids
    rows = [r for r in d["items"] if not r.get("is_header")]
    r = client.post(f"/purchase/from-draft/{d['id']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "dl_line_id": [x["line_id"] for x in rows],
        "dl_qty": ["1"] * len(rows), "dl_rate": ["100"] * len(rows)})
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    po = next(iter(STORE["purchases"].values()))
    names = [x["name"] for x in po["line_items"]]
    assert "Something not on the schedule" in names


def test_a_line_is_removed(client, shop):
    d = _a_draft(client, shop)
    items = [r for r in d["items"] if not r.get("is_header")]
    assert len(items) >= 2
    gone = d["items"].index(items[0])
    desc = items[0]["description"]
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, drop={gone}))
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    assert desc not in [x["description"] for x in d["items"]]
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert desc not in html


def test_a_specification_row_is_added_and_carries_no_quantity(client, shop):
    d = _a_draft(client, shop)
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, add=[
        {"is_header": True, "item_no": "B", "description": "Clause: IS 5312"}]))
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    row = d["items"][-1]
    assert row["is_header"] is True
    assert row["description"] == "Clause: IS 5312"
    assert row["qty"] == 0.0 and row["unit"] == "" and row["pcs"] == ""
    assert "make" not in row and "hsn" not in row
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert "Clause: IS 5312" in html
    assert 'class="row-assembly"' in html


def test_emptying_every_line_is_refused_and_writes_nothing(client, shop):
    d = _a_draft(client, shop)
    was = [dict(r) for r in d["items"]]
    r = client.post(f"/po/edit/{d['id']}",
                    data=_rows(d, drop=set(range(len(d["items"])))))
    assert r.status_code == 200
    assert "nothing on this document to price" in r.get_data(as_text=True)
    assert d["items"] == was


def test_a_stale_tab_with_no_line_boxes_leaves_every_line_alone(client, shop):
    """
    `purchase._reprice()`'s rule, because the alternative is a save that
    silently empties a document.
    """
    d = _a_draft(client, shop)
    was = [dict(r) for r in d["items"]]
    r = client.post(f"/po/edit/{d['id']}", data={
        "date": "2026-11-01", "vendor_id": VENDOR_ID, "notes": "moved on"})
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    assert d["items"] == was
    assert d["date"] == "2026-11-01" and d["notes"] == "moved on"


# ═══ 3. Refusals, and nothing written on one ════════════════════════════════

def test_a_figure_with_no_description_is_refused(client, shop):
    d = _a_draft(client, shop)
    was = [dict(r) for r in d["items"]]
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, add=[
        {"unit": "Nos", "qty": "4"}]))
    assert r.status_code == 200
    assert "has figures but no description" in r.get_data(as_text=True)
    assert d["items"] == was


def test_text_typed_into_the_quantity_box_is_refused(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    was = [dict(r) for r in d["items"]]
    r = client.post(f"/po/edit/{d['id']}",
                    data=_rows(d, {n: {"qty": "twelve"}}))
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "is not a number" in body
    assert d["items"] == was
    assert 'value="twelve"' in body, "a refused save must hand back what was typed"


def test_a_negative_quantity_is_refused(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    was = [dict(r) for r in d["items"]]
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"qty": "-3"}}))
    assert r.status_code == 200
    assert "cannot be negative" in r.get_data(as_text=True)
    assert d["items"] == was


def test_a_refused_save_hands_back_every_row_including_the_added_one(client, shop):
    d = _a_draft(client, shop)
    r = client.post(f"/po/edit/{d['id']}", data=_rows(d, add=[
        {"description": "A good row", "unit": "Nos", "qty": "2"},
        {"unit": "Nos", "qty": "9"}]))
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "A good row" in body, "the row that was fine came back"
    assert 'value="9"' in body, "and so did the one that was not"


def test_a_vendor_refusal_leaves_the_lines_alone(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    was = [dict(r) for r in d["items"]]
    body = _rows(d, {n: {"description": "Changed"}})
    body["vendor_id"] = ""
    body["vendor_name"] = ""
    r = client.post(f"/po/edit/{d['id']}", data=body)
    assert r.status_code == 200
    assert "Choose a vendor" in r.get_data(as_text=True)
    assert d["items"] == was


def test_a_posted_line_id_that_is_not_on_this_draft_is_re_minted(client, shop):
    """
    ⚠ `line_id` is what the Pictures page addresses a row by and what
    `purchase.from_draft()` matches a posted quantity on. A posted one is
    therefore kept only when it is the minted shape AND already on this
    draft — otherwise a crafted POST could make two drafts claim the same id,
    or point a row at another document's line.
    """
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    mine = d["items"][n]["line_id"]
    body = _rows(d)
    body["it_line_id"][n] = "deadbeefcafe"          # right shape, not on this draft
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    now = d["items"][n]["line_id"]
    assert now != "deadbeefcafe" and now != mine
    assert BQ._line_id(now) == now, "and it is a properly minted id"


def test_a_posted_line_id_is_re_minted_rather_than_duplicated(client, shop):
    d = _a_draft(client, shop)
    items = [i for i, r in enumerate(d["items"]) if not r.get("is_header")]
    assert len(items) >= 2
    a, b = items[0], items[1]
    body = _rows(d)
    body["it_line_id"][b] = body["it_line_id"][a]    # the same id twice
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    ids = [r["line_id"] for r in d["items"]]
    assert len(ids) == len(set(ids)), "two rows ended up sharing a line_id"


def test_a_quantity_posted_on_a_specification_row_is_dropped(client, shop):
    """
    DOMAIN.md §2.2: the clause carries no quantity. A crafted POST must not
    give one a figure, because the printed sheet draws a header row with no
    Qty cell at all and the figure would simply vanish on paper while sitting
    in the record.
    """
    d = _a_draft(client, shop)
    body = _rows(d, add=[{"is_header": True, "item_no": "C",
                          "description": "Clause: a quantity is not allowed"}])
    # The header row the helper just appended, with a quantity forced on.
    body["it_qty"][-1] = "99"
    body["it_unit"][-1] = "Nos"
    body["it_pcs"][-1] = "5"
    body["it_make"][-1] = "SANT"
    body["it_hsn"][-1] = "73072900"
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    row = d["items"][-1]
    assert row["is_header"] is True
    assert row["qty"] == 0.0 and row["unit"] == "" and row["pcs"] == ""
    assert "make" not in row and "hsn" not in row


def test_the_line_cap_is_enforced_on_the_editor(client, shop, monkeypatch):
    """
    Lowered rather than posting 600 rows: the assertion is that the cap is
    READ, and `MAX_PO_LINES` is derived from `boq.MAX_LINES` by the test below.
    """
    d = _a_draft(client, shop)
    monkeypatch.setattr(PD, "MAX_PO_LINES", 2)
    was = [dict(r) for r in d["items"]]
    body = _rows(d, add=[{"description": f"Extra {i}", "unit": "Nos", "qty": "1"}
                         for i in range(3)])
    r = client.post(f"/po/edit/{d['id']}", data=body)
    assert r.status_code == 200
    assert "the limit is 2" in r.get_data(as_text=True)
    assert d["items"] == was


def test_a_refused_line_leaves_every_other_field_alone_too(client, shop):
    """
    Nothing is written on a refusal — not the vendor, not the date, not the
    notes, and not the lines that were fine. `parse_items()` stages and the
    route returns before a single assignment.
    """
    d = _a_draft(client, shop)
    was = [dict(r) for r in d["items"]]
    was_date, was_notes, was_to = d["date"], d["notes"], d["delivery_to"]
    body = _rows(d, add=[{"unit": "Nos", "qty": "4"}])   # figures, no description
    body["date"] = "2099-12-31"
    body["notes"] = "should not land"
    body["delivery_to"] = "nor this"
    r = client.post(f"/po/edit/{d['id']}", data=body)
    assert r.status_code == 200
    assert d["items"] == was
    assert d["date"] == was_date and d["notes"] == was_notes
    assert d["delivery_to"] == was_to


def test_the_line_cap_is_the_boqs(client, shop):
    assert PD.MAX_PO_LINES == BQ.MAX_LINES


# ═══ 4. THE LOCK — hidden on the GET, REFUSED on the POST ══════════════════

def _convert(client, shop, d):
    rows = [r for r in d["items"] if not r.get("is_header")]
    r = client.post(f"/purchase/from-draft/{d['id']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "dl_line_id": [x["line_id"] for x in rows],
        "dl_qty": ["1"] * len(rows), "dl_rate": ["100"] * len(rows)})
    assert r.status_code == 302, r.get_data(as_text=True)[:900]
    return next(iter(STORE["purchases"].values()))


def test_an_unconverted_draft_is_not_locked(client, shop):
    d = _a_draft(client, shop)
    assert PD.is_locked(d) is False
    assert client.get(f"/po/edit/{d['id']}").status_code == 200


def test_a_converted_draft_is_locked_on_the_GET(client, shop):
    d = _a_draft(client, shop)
    _convert(client, shop, d)
    assert PD.is_locked(d) is True
    r = client.get(f"/po/edit/{d['id']}")
    assert r.status_code == 302
    assert f"/po/view/{d['id']}" in r.headers["Location"]
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "already been converted" in body


def test_a_converted_draft_is_REFUSED_ON_THE_POST_and_nothing_is_written(client, shop):
    """
    ⚠ **The assertion A2 exists for.** A form that is merely not drawn is not
    a lock: this hits the POST directly, exactly as a bookmarked tab or a
    typed request would.
    """
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    body = _rows(d, {n: {"description": "SNEAKED IN", "qty": "999"}})
    body["notes"] = "sneaked"
    body["date"] = "2099-01-01"
    _convert(client, shop, d)
    was = [dict(r) for r in d["items"]]
    was_notes, was_date = d["notes"], d["date"]

    r = client.post(f"/po/edit/{d['id']}", data=body)
    assert r.status_code == 302
    assert f"/po/view/{d['id']}" in r.headers["Location"]
    assert d["items"] == was, "a converted draft's lines were written"
    assert d["notes"] == was_notes and d["date"] == was_date
    assert "SNEAKED IN" not in client.get(
        f"/po/print/{d['id']}").get_data(as_text=True)


def test_the_lock_lifts_if_the_order_it_names_is_deleted(client, shop):
    """
    `is_locked()` reads `converted_pos()`, which drops an order that no longer
    exists — so there is no longer an order whose provenance this document is,
    and it is editable again. Deliberate, and the reason it is not a stored
    flag.
    """
    d = _a_draft(client, shop)
    po = _convert(client, shop, d)
    assert PD.is_locked(d) is True
    assert client.post(f"/purchase/delete/{po['id']}").status_code == 302
    assert PD.is_locked(d) is False
    assert client.get(f"/po/edit/{d['id']}").status_code == 200


def test_the_view_page_greys_the_edit_control_once_converted(client, shop):
    d = _a_draft(client, shop)
    before = client.get(f"/po/view/{d['id']}").get_data(as_text=True)
    assert f'href="/po/edit/{d["id"]}"' in before
    _convert(client, shop, d)
    after = client.get(f"/po/view/{d['id']}").get_data(as_text=True)
    assert f'href="/po/edit/{d["id"]}"' not in after
    assert "cursor:not-allowed" in after and "Already converted" in after


# ═══ 5. The number keeps its existing rules ════════════════════════════════

def test_a_full_edit_never_reissues_the_number(client, shop):
    d = _a_draft(client, shop)
    ref = d["ref"]
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"qty": "9"}}))
    assert d["ref"] == ref
    assert int(SET.po_series()["next_no"]) == 2, "the counter did not move"


# ═══ 6. No rate, anywhere — the recorded conflict, pinned ══════════════════

def test_there_is_no_rate_box_on_the_editor(client, shop):
    """
    A2's brief named "rate" among the editable fields and Manas's answer, with
    `PRINT_RATES` and the module docstring put to him, was: **no rate box.**
    Pinned so a later pass has to take that decision again rather than drift
    into it, and so the prohibition the docstring states stays true.
    """
    d = _a_draft(client, shop)
    page = client.get(f"/po/edit/{d['id']}").get_data(as_text=True)
    assert 'name="it_rate"' not in page
    assert PD.PRINT_RATES is False
    # The printed Rate column is present and EMPTY, as it always was.
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert '<td class="c-rate-blank"></td>' in html


def test_the_editor_never_stores_a_rate_even_if_one_is_posted(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    body = _rows(d, {n: {"qty": "4"}})
    body["it_rate"] = ["1234"] * len(body["it_kind"])
    body["rate"] = "1234"
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    for row in d["items"]:
        assert "rate" not in row and "price" not in row


def test_no_boq_supply_rate_reaches_the_document(client, shop):
    """The one thing this document must never do, re-asserted after the edit."""
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"qty": "4"}}))
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    for li in STORE["boqs"][shop["boq"]]["line_items"]:
        for key in ("supply_rate", "supply_base_rate", "supply_amount"):
            v = li.get(key)
            if v:
                assert f"{float(v):,.2f}" not in html, f"{key} leaked"


# ═══ 7. HSN flows through this document ════════════════════════════════════

def test_the_schedules_hsn_is_snapshotted_at_create(client, shop):
    bid = shop["boq"]
    lid = BQ._line_id(shop["lines"][0]["line_id"])
    # One line with a code, every other line with none, so BOTH halves are
    # asserted on this one record.
    STORE["boqs"][bid]["line_items"] = [
        dict(li, supply_hsn=("73069090" if BQ._line_id(li.get("line_id")) == lid else ""))
        for li in STORE["boqs"][bid]["line_items"]]
    d = _a_draft(client, shop)
    row = next(r for r in d["items"] if r.get("line_id") == lid)
    assert row["hsn"] == "73069090"
    other = next(r for r in d["items"]
                 if not r.get("is_header") and r["line_id"] != lid)
    assert "hsn" not in other, "no empty key on a line the schedule had none for"


def test_the_drafts_own_hsn_beats_the_schedules_on_conversion(client, shop):
    bid = shop["boq"]
    lid = BQ._line_id(shop["lines"][0]["line_id"])
    STORE["boqs"][bid]["line_items"] = [
        dict(li, supply_hsn=("73069090" if BQ._line_id(li.get("line_id")) == lid else ""))
        for li in STORE["boqs"][bid]["line_items"]]
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if r.get("line_id") == lid)
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"hsn": "84818030"}}))
    po = _convert(client, shop, d)
    row = next(x for x in po["line_items"] if x.get("line_id") == lid)
    assert row["hsn"] == "84818030", (
        "the draft's own code is the more recent answer and the one the "
        "supplier was asked about")


def test_the_inquiry_prints_no_hsn_column(client, shop):
    """
    A request for quotation carries no tax block at all (`PRINT_TAX`), and an
    HSN is a tax code. The field rides into the real purchase order instead.
    """
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"hsn": "84818030"}}))
    html = client.get(f"/po/print/{d['id']}").get_data(as_text=True)
    assert PD.PRINT_TAX is False
    assert "84818030" not in html
    assert 'class="c-hsn"' not in html


# ═══ 8. The picture rides on its own row ═══════════════════════════════════

def test_a_pictures_id_survives_an_edit_that_reorders_nothing(client, shop):
    import lineimage as LI
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    # A real file, so `LI.exists()` lets it through — an id alone is refused.
    from test_line_pictures import _saved
    iid = _saved()
    assert iid, "the fixture did not produce a picture"
    d["items"][n][LI.KEY] = iid
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {"description": "Changed"}}))
    assert d["items"][n].get(LI.KEY) == iid
    assert d["items"][n]["description"] == "Changed"


def test_an_invented_picture_id_is_dropped(client, shop):
    import lineimage as LI
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    body = _rows(d)
    body["it_image"][n] = "f" * 64          # the right shape, no file behind it
    assert client.post(f"/po/edit/{d['id']}", data=body).status_code == 302
    assert LI.KEY not in d["items"][n]


# ═══ 9. Escaping ═══════════════════════════════════════════════════════════

PAYLOAD = "<script>alert(1)</script>\"'&<img src=x onerror=alert(2)>"


def test_a_hostile_line_is_escaped_on_the_form_and_on_the_document(client, shop):
    d = _a_draft(client, shop)
    n = next(i for i, r in enumerate(d["items"]) if not r.get("is_header"))
    client.post(f"/po/edit/{d['id']}", data=_rows(d, {n: {
        "description": PAYLOAD, "item_no": PAYLOAD, "unit": PAYLOAD[:30],
        "make": PAYLOAD[:60], "pcs": PAYLOAD[:16]}}))
    for url in (f"/po/edit/{d['id']}", f"/po/view/{d['id']}",
                f"/po/print/{d['id']}"):
        body = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in body, url
        assert "<img src=x onerror=alert(2)>" not in body, url
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body, url
