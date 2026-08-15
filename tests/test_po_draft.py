"""
The draft purchase order — CLIENT_CHANGES.md item 4.

Four client constraints, and each one is a section below:

  * **description and quantity only, rates blank** — nothing on the document
    may read a buy rate from anywhere, because it goes to a supplier *to be
    priced*;
  * **no GST**, not a zero-rated block;
  * **one running number series** across all suppliers and all sites,
    continuing the numbers already kept on paper;
  * only the lines the operator **ticked**.

That last one is why this file was rewritten. The first implementation
snapshotted every line of the BOQ tip unconditionally: on the client's own
97-line schedule that produced a 97-line purchase order for a supplier being
asked to price four of them, and there was no checkbox anywhere.

⚠ Two of the original three tests here passed against code that was broken, and
  the way they did it is worth knowing. `po_draft` read `line["desc"]` and
  `line["type"]` off a BOQ line, and a BOQ line carries **`description`** and
  **`is_header`** — so every snapshotted row had an empty description and no
  header was ever recognised. The immutability test then asserted
  `po["items"][0]["desc"] in html`, which is `"" in html`: **true of every page
  ever rendered.** An assertion that a value survives has to be an assertion
  about a value that exists.
"""

import json

import pytest

import boq as BQ
import po_draft
import settings as SET
from store import STORE


@pytest.fixture()
def boq_tip(client):
    """The seeded 97-line Sify schedule, and a clean PO collection."""
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    bid = next(b for b, rec in STORE["boqs"].items() if not rec.get("supersedes"))
    yield bid
    STORE["purchase_orders"].clear()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)


@pytest.fixture()
def vendor(client):
    import address
    address.ensure_demo_addresses()
    return next(a["id"] for a in STORE["addresses"].values()
                if a.get("type") == "vendor")


def _lines_of(bid):
    return [li for li in STORE["boqs"][bid]["line_items"]
            if not li.get("is_header")]


def _payload(lines, qty=None, pcs=None):
    return json.dumps({"lines": [
        {"line_id": li["line_id"],
         "qty": "" if qty is None else str(qty),
         "pcs": "" if pcs is None else str(pcs)} for li in lines]})


def _create(client, bid, vendor_id, lines, **extra):
    data = {"date": "2026-08-15", "vendor_id": vendor_id,
            "notes": "", "po_json": _payload(lines)}
    data.update(extra)
    return client.post(f"/po/create?boq={bid}", data=data)


def _only_po():
    return next(iter(STORE["purchase_orders"].values()))


# ═══ 1. The item picker — the part that was missing entirely ═══════════════

def test_the_create_form_lists_every_boq_line_with_a_checkbox(client, boq_tip, vendor):
    """One row per line, a box on each, and a select-all / clear-all control."""
    html = client.get(f"/po/create?boq={boq_tip}").get_data(as_text=True)

    for li in _lines_of(boq_tip):
        assert f'id="c_{li["line_id"]}"' in html, \
            f'line {li["item_no"]} has no checkbox'
        assert f'id="q_{li["line_id"]}"' in html, \
            f'line {li["item_no"]} has no quantity box'
    assert "selectAll()" in html and "clearAll()" in html


def test_every_box_arrives_ticked(client, boq_tip, vendor):
    """
    Most orders are the whole schedule, so the common case must be the cheap
    one. A form opening with 97 empty boxes would make it the expensive one.
    """
    html = client.get(f"/po/create?boq={boq_tip}").get_data(as_text=True)
    for li in _lines_of(boq_tip)[:20]:
        marker = f'id="c_{li["line_id"]}" checked'
        assert marker in html, f'line {li["item_no"]} did not arrive ticked'


def test_the_quantity_defaults_to_the_boq_quantity(client, boq_tip, vendor):
    html = client.get(f"/po/create?boq={boq_tip}").get_data(as_text=True)
    li = next(l for l in _lines_of(boq_tip) if float(l["total_qty"] or 0) > 0)
    assert f'id="q_{li["line_id"]}"\n              value="{BQ._fmt_qty(li["total_qty"])}"' \
           in html.replace("\r\n", "\n")


def test_all_lines_ticked_snapshots_all_of_them(client, boq_tip, vendor):
    lines = _lines_of(boq_tip)
    assert _create(client, boq_tip, vendor, lines).status_code == 302
    po = _only_po()
    priced = [r for r in po["items"] if not r["is_header"]]
    assert len(priced) == len(lines)


def test_a_subset_ticked_snapshots_only_that_subset(client, boq_tip, vendor):
    """
    The whole point. Three lines ticked out of 87 must produce a three-line
    purchase order, not the schedule.
    """
    lines = _lines_of(boq_tip)
    chosen = lines[:3]
    assert _create(client, boq_tip, vendor, chosen).status_code == 302

    po = _only_po()
    priced = [r for r in po["items"] if not r["is_header"]]
    assert len(priced) == 3, f"expected 3 lines, got {len(priced)}"
    assert {r["line_id"] for r in priced} == {li["line_id"] for li in chosen}
    # And the 84 that were not ticked are genuinely absent.
    left_out = {li["line_id"] for li in lines[3:]}
    assert not ({r["line_id"] for r in priced} & left_out)


def test_no_lines_ticked_is_refused_and_writes_nothing(client, boq_tip, vendor):
    """An empty PO is not a document. It is refused with a reason, not saved."""
    r = client.post(f"/po/create?boq={boq_tip}", data={
        "date": "2026-08-15", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": []})})

    assert r.status_code == 200, "an empty selection was accepted"
    assert "No lines are ticked" in r.get_data(as_text=True)
    assert not STORE["purchase_orders"], "an empty PO was written"


def test_a_per_line_quantity_override_is_carried_onto_the_print(client, boq_tip, vendor):
    """
    The quantity is editable and what was typed is what prints — not the BOQ's
    figure, and not silently either one.
    """
    li = next(l for l in _lines_of(boq_tip) if float(l["total_qty"] or 0) > 50)
    r = client.post(f"/po/create?boq={boq_tip}", data={
        "date": "2026-08-15", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": [
            {"line_id": li["line_id"], "qty": "7", "pcs": "3"}]})})
    assert r.status_code == 302

    po = _only_po()
    row = next(r_ for r_ in po["items"] if not r_["is_header"])
    assert row["qty"] == 7.0
    assert row["pcs"] == "3"

    html = client.get(f"/po/print/{po['id']}").get_data(as_text=True)
    assert ">7<" in html, "the overridden quantity did not reach the document"
    assert f">{BQ._fmt_qty(li['total_qty'])}<" not in html, \
        "the BOQ quantity printed instead of the one that was typed"


def test_a_ticked_line_brings_its_specification_header_with_it(client, boq_tip, vendor):
    """
    A parent clause prints above its sizes, carrying no quantity — DOMAIN.md
    §2.2. This is also the regression: `is_header` was read as `type`, so no
    header was ever recognised and the clause never came across.
    """
    boq = STORE["boqs"][boq_tip]
    child = next(li for li in boq["line_items"]
                 if not li.get("is_header") and li.get("parent_item_no"))
    assert _create(client, boq_tip, vendor, [child]).status_code == 302

    po = _only_po()
    heads = [r for r in po["items"] if r["is_header"]]
    assert len(heads) == 1, "the specification clause did not come with its size"
    assert heads[0]["item_no"] == child["parent_item_no"]
    assert heads[0]["description"].strip(), "the clause came across empty"
    assert heads[0]["qty"] == 0.0, "a specification header must carry no quantity"


# ═══ 2. The snapshot ═══════════════════════════════════════════════════════

def test_every_snapshotted_row_carries_a_real_description(client, boq_tip, vendor):
    """
    The control for this whole file.

    `po_draft` read `line["desc"]`, which a BOQ line does not have, so every row
    was snapshotted with an empty description — and the old immutability test
    asserted `"" in html` and passed. Assert the descriptions are non-empty
    before believing anything else here.
    """
    lines = _lines_of(boq_tip)[:5]
    assert _create(client, boq_tip, vendor, lines).status_code == 302
    po = _only_po()
    for row in po["items"]:
        assert row["description"].strip(), \
            f'row {row["item_no"]} was snapshotted with no description'


def test_the_print_is_driven_by_the_pos_own_rows_not_the_live_boq(client, boq_tip, vendor):
    """
    CLIENT_CHANGES.md §1.2. Revising the schedule underneath an existing draft
    PO must not change what that PO says.
    """
    lines = _lines_of(boq_tip)[:4]
    assert _create(client, boq_tip, vendor, lines).status_code == 302
    po = _only_po()
    before = client.get(f"/po/print/{po['id']}").get_data(as_text=True)

    boq = STORE["boqs"][boq_tip]
    boq["project_name"] = "MODIFIED PROJECT"
    boq["line_items"][0]["description"] = "MODIFIED DESCRIPTION"
    boq["line_items"][0]["item_no"] = "999"
    del boq["line_items"][1]

    after = client.get(f"/po/print/{po['id']}").get_data(as_text=True)
    assert after == before, "the document moved when the schedule under it did"
    assert "MODIFIED PROJECT" not in after
    assert "MODIFIED DESCRIPTION" not in after


def test_a_posted_line_id_that_is_not_on_this_boq_is_dropped(client, boq_tip, vendor):
    """
    CLIENT_CHANGES.md §1.4: matching is on `line_id` and a row that matches
    nothing is skipped, never guessed back through `item_no`.
    """
    good = _lines_of(boq_tip)[0]
    r = client.post(f"/po/create?boq={boq_tip}", data={
        "date": "2026-08-15", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": [
            {"line_id": good["line_id"], "qty": "", "pcs": ""},
            {"line_id": "ffffffffffff", "qty": "99", "pcs": ""}]})})
    assert r.status_code == 302
    priced = [x for x in _only_po()["items"] if not x["is_header"]]
    assert len(priced) == 1
    assert priced[0]["line_id"] == good["line_id"]


# ═══ 3. No GST, and no rates ═══════════════════════════════════════════════

def test_the_document_carries_no_gst_of_any_kind(client, boq_tip, vendor):
    """Not a zero-rated block — no block at all."""
    assert _create(client, boq_tip, vendor, _lines_of(boq_tip)[:3]).status_code == 302
    po = _only_po()
    for url in (f"/po/view/{po['id']}", f"/po/print/{po['id']}"):
        html = client.get(url).get_data(as_text=True)
        for token in ("CGST", "SGST", "IGST", "Taxable Value"):
            assert token not in html, f"{url} mentions {token}"
    assert po_draft.PRINT_TAX is False


def test_no_rate_from_anywhere_reaches_the_document(client, boq_tip, vendor):
    """
    Rates are blank BY DESIGN. The BOQ's supply rate is what we sell the work
    for, and putting it in front of the supplier quoting us is the one thing
    this document must never do.
    """
    li = next(l for l in _lines_of(boq_tip) if float(l.get("supply_rate") or 0) > 1000)
    assert _create(client, boq_tip, vendor, [li]).status_code == 302
    po = _only_po()

    assert "rate" not in {k.lower() for row in po["items"] for k in row}
    html = client.get(f"/po/print/{po['id']}").get_data(as_text=True)
    rate_text = f"{float(li['supply_rate']):,.2f}"
    assert rate_text not in html, "the BOQ's supply rate reached the supplier's copy"
    assert po_draft.PRINT_RATES is False


# ═══ 4. Numbering — one global series, and a number is never released ══════

def test_the_series_is_global_and_not_per_boq(client, boq_tip, vendor):
    """
    **The opposite of `ra_no`, deliberately.** One running series across all
    suppliers and all sites, so raising an order against a second schedule
    continues the same run rather than restarting it.
    """
    lines = _lines_of(boq_tip)[:2]
    assert _create(client, boq_tip, vendor, lines).status_code == 302

    # A second, unrelated BOQ.
    other = "boq-other"
    STORE["boqs"][other] = dict(STORE["boqs"][boq_tip], id=other,
                                ref="SF/BOQ/26-27/0002",
                                project_name="A different site", supersedes="")
    assert _create(client, other, vendor, lines).status_code == 302

    refs = sorted(po["ref"] for po in STORE["purchase_orders"].values())
    assert refs == ["SF/DPO/0001", "SF/DPO/0002"], refs
    STORE["boqs"].pop(other, None)


def test_the_prefix_and_next_number_are_editable_at_settings(client, boq_tip, vendor):
    """
    The client's series already exists on paper. Hardcoding `SF/DPO/0001` would
    collide with their book on the first order.
    """
    r = client.post("/settings/", data={"po_prefix": "SFS/PO",
                                        "po_next_no": "417"})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert SET.po_series() == {"prefix": "SFS/PO", "next_no": "417"}

    assert _create(client, boq_tip, vendor, _lines_of(boq_tip)[:1]).status_code == 302
    assert _only_po()["ref"] == "SFS/PO/0417"


def test_a_deleted_draft_po_does_not_release_its_number(client, boq_tip, vendor):
    """
    The number has been quoted to a supplier. A second document bearing it is
    indistinguishable from the first — the same reasoning that stops a GST
    serial being reissued.
    """
    lines = _lines_of(boq_tip)[:1]
    assert _create(client, boq_tip, vendor, lines).status_code == 302
    first = _only_po()
    assert first["ref"] == "SF/DPO/0001"

    assert client.post(f"/po/delete/{first['id']}").status_code == 302
    assert not STORE["purchase_orders"]

    assert _create(client, boq_tip, vendor, lines).status_code == 302
    assert _only_po()["ref"] == "SF/DPO/0002", \
        "the deleted PO handed its number back"


def test_an_edit_never_reissues_the_number(client, boq_tip, vendor):
    assert _create(client, boq_tip, vendor, _lines_of(boq_tip)[:1]).status_code == 302
    po = _only_po()
    ref, pid = po["ref"], po["id"]

    r = client.post(f"/po/edit/{pid}", data={
        "date": "2026-09-01", "vendor_id": vendor, "notes": "revised"})
    assert r.status_code == 302
    assert STORE["purchase_orders"][pid]["ref"] == ref


# ═══ 5. The vendor — picker, with a free-text fallback ═════════════════════

def test_the_address_book_vendor_is_snapshotted_onto_the_po(client, boq_tip, vendor):
    assert _create(client, boq_tip, vendor, _lines_of(boq_tip)[:1]).status_code == 302
    po = _only_po()
    book = STORE["addresses"][vendor]

    assert po["vendor_source"] == "book"
    assert po["vendor_id"] == vendor
    assert po["vendor_name"] == (book.get("company") or book.get("contact_name"))
    assert po["to"].strip(), "the vendor address was not snapshotted"

    # And it survives the address book being edited underneath it.
    before = client.get(f"/po/print/{po['id']}").get_data(as_text=True)
    book["company"] = "RENAMED VENDOR LTD"
    assert client.get(f"/po/print/{po['id']}").get_data(as_text=True) == before


def test_a_one_off_supplier_can_be_typed_instead(client, boq_tip):
    """
    The brief said free-text party fields. The address book is better and is
    kept as the primary path — but a local fabricator quoting one job should
    not have to be filed before they can be asked for a price.
    """
    r = client.post(f"/po/create?boq={boq_tip}", data={
        "date": "2026-08-15", "vendor_id": "",
        "vendor_name": "Shree Fabricators (one-off)",
        "vendor_gstin": "27ABCDE1234F1Z5",
        "vendor_addr": "Shed 4, MIDC Rabale",
        "notes": "", "po_json": _payload(_lines_of(boq_tip)[:1])})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]

    po = _only_po()
    assert po["vendor_source"] == "typed"
    assert po["vendor_id"] == ""
    assert po["vendor_name"] == "Shree Fabricators (one-off)"
    assert po["vendor_gstin"] == "27ABCDE1234F1Z5"

    html = client.get(f"/po/print/{po['id']}").get_data(as_text=True)
    assert "Shree Fabricators (one-off)" in html
    assert "Shed 4, MIDC Rabale" in html


def test_neither_vendor_path_given_is_refused(client, boq_tip):
    r = client.post(f"/po/create?boq={boq_tip}", data={
        "date": "2026-08-15", "vendor_id": "", "vendor_name": "",
        "notes": "", "po_json": _payload(_lines_of(boq_tip)[:1])})
    assert r.status_code == 200
    assert "type a one-off supplier" in r.get_data(as_text=True)
    assert not STORE["purchase_orders"]


# ═══ 6. Routes and the sheet ═══════════════════════════════════════════════

def test_the_draft_po_prints_on_the_same_sheet_as_the_buy_side_po(client, boq_tip, vendor):
    """
    Separate behaviour, shared appearance. The two documents differ on GST,
    rates and the Pcs column — and on nothing about the letterhead, the party
    block, the table shell or the signature.
    """
    assert _create(client, boq_tip, vendor, _lines_of(boq_tip)[:2]).status_code == 302
    html = client.get(f"/po/print/{_only_po()['id']}").get_data(as_text=True)

    assert 'class="page-frame"' in html, "no shared page frame"
    assert 'class="lh-name"' in html, "no letterhead"
    assert 'class="doc-header"' in html, "no shared party block"
    assert 'class="q-table"' in html, "not the shared items table"
    assert 'class="sig-block"' in html, "no signature block"
    assert ">Pcs</th>" in html, "the client's Pcs column is missing"


def test_a_superseded_boq_is_refused_at_the_route(client, boq_tip, vendor):
    STORE["boqs"]["newer"] = dict(STORE["boqs"][boq_tip], id="newer",
                                  ref="SF/BOQ/26-27/0009", supersedes=boq_tip)
    try:
        r = client.get(f"/po/create?boq={boq_tip}")
        assert r.status_code == 302
        assert "superseded" in r.headers["Location"].lower()
    finally:
        STORE["boqs"].pop("newer", None)


def test_get_on_po_delete_destroys_nothing(client, boq_tip, vendor):
    """
    ABOUT.md §7.9f's standing rule for a NEW delete route: it ships its own
    per-route GET test. The `url_map` sweep proves only that the rule accepts
    POST — it cannot catch a route that accepts both and still destroys on GET.
    """
    assert _create(client, boq_tip, vendor, _lines_of(boq_tip)[:1]).status_code == 302
    pid = _only_po()["id"]

    r = client.get(f"/po/delete/{pid}")
    assert r.status_code == 200
    assert pid in STORE["purchase_orders"], "a GET destroyed the record"

    r = client.post(f"/po/delete/{pid}")
    assert r.status_code == 302
    assert pid not in STORE["purchase_orders"]
