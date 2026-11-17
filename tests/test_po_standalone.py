"""
A Product Inquiry WITHOUT a BOQ, and EXTRA items on any inquiry
(17 November 2026, CLIENT_CHANGES.md §0 seventy-sixth block).

What this file holds:

  * a no-BOQ inquiry is raised from `/po/create?noboq=1`, `boq_id` None, in
    the SAME `SF/DPO` series and counter, its lines being extra items only,
    with an optional project snapshotted;
  * extra items ride on a BOQ inquiry after the BOQ lines, `line_id` None and
    `extra` True, typed or picked from the specification library — which is
    never written — on create AND on edit;
  * CONVERT TO PURCHASE ORDER carries extras into the real order's extra
    lines, the rate opening at the library's supply base rate (blank when it
    has none), while BOQ lines convert exactly as before;
  * a no-BOQ inquiry with a project shows on that project's page, and the
    project P&L does not move (an inquiry carries no money);
  * the print is the inquiry's own rows on the unchanged sheet (the BOQ print
    golden in `test_print_golden.py` is the byte check).
"""

import copy

import pytest
from werkzeug.datastructures import MultiDict

import buypick as BYP
import pnl
import po_draft
import settings as SET
from store import STORE

from tests.test_boq_to_po import PROJECT_ID, VENDOR_ID, shop  # noqa: F401

PID = "p-dpo"


def _extras(*rows):
    """`rows` = (desc, qty, unit[, pick[, make[, pcs]]]) → the posted lists."""
    md = []
    for r in rows:
        r = tuple(r) + ("",) * (6 - len(r))
        md += [("xi_desc", r[0]), ("xi_qty", r[1]), ("xi_unit", r[2]),
               ("line_product_id", r[3]), ("xi_make", r[4]), ("xi_pcs", r[5]),
               ("xi_image", "")]
    return md


def _post(client, url, base, rows=()):
    return client.post(url, data=MultiDict(list(base.items()) + _extras(*rows)))


def _base(**over):
    d = {"date": "2026-11-17", "vendor_name": "Local Fabricator", "notes": "",
         "delivery_to": "", "xi_present": "1"}
    d.update(over)
    return d


def _dpos():
    return STORE.setdefault("purchase_orders", {})


def _spec_pick():
    """A library variant that HAS a supply base rate."""
    BYP.ensure_seeded()
    e = next(e for e in BYP.spec_entries() if e["rate"])
    return e["value"], e["rate"], e["name"]


@pytest.fixture()
def clean(client):
    _dpos().clear()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    STORE.setdefault("projects", {})[PID] = {
        "id": PID, "name": "Chakan Plant", "norm_name": "chakan plant",
        "client": "X", "notes": "", "site_address_id": "", "site_address": "",
        "created_at": "2026-11-01 09:00", "updated_at": "2026-11-01 09:00"}
    yield client
    _dpos().clear()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    STORE["projects"].pop(PID, None)


# ── An inquiry without a BOQ ────────────────────────────────────────────────

def test_the_register_offers_a_new_inquiry_without_a_boq(clean):
    html = clean.get("/po/").get_data(as_text=True)
    assert 'href="/po/create?noboq=1"' in html
    assert "New Product Inquiry (no BOQ)" in html
    form = clean.get("/po/create?noboq=1")
    assert form.status_code == 200
    page = form.get_data(as_text=True)
    assert "without a bill of quantities" in page
    assert 'name="xi_desc"' in page and 'name="project_id"' in page
    assert "Import from Excel" not in page
    # A stale or missing ?boq= still refuses as before.
    assert clean.get("/po/create").status_code == 302


def test_a_no_boq_inquiry_is_saved_in_the_same_series(clean):
    SET.save_po_series("SF/DPO", 41)
    r = _post(clean, "/po/create?noboq=1", _base(project_id=PID),
              [("Fire hose reel drum", "2", "Nos", "", "Newage", "4")])
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    po = next(iter(_dpos().values()))
    assert po["boq_id"] is None and po["ref"] == "SF/DPO/0041"
    assert int(SET.po_series()["next_no"]) == 42
    assert (po["project_id"], po["project_name"]) == (PID, "Chakan Plant")
    assert po["vendor_source"] == "typed" and po["vendor_name"] == "Local Fabricator"
    [row] = po["items"]
    assert row["line_id"] is None and row["extra"] is True
    assert (row["description"], row["qty"], row["unit"], row["make"], row["pcs"]) == (
        "Fire hose reel drum", 2.0, "Nos", "Newage", "4")

    pr = clean.get(f"/po/print/{po['id']}").get_data(as_text=True)
    assert po_draft.DOC_TITLE in pr and "Fire hose reel drum" in pr
    assert "Newage" in pr and "Chakan Plant" in pr
    view = clean.get(f"/po/view/{po['id']}").get_data(as_text=True)
    assert "/boq/view/" not in view.split('class="doc-outer"')[0]
    reg = clean.get("/po/").get_data(as_text=True)
    assert "SF/DPO/0041" in reg


def test_a_no_boq_inquiry_with_nothing_on_it_is_refused(clean):
    r = _post(clean, "/po/create?noboq=1", _base(), [])
    assert r.status_code == 200
    assert "nothing on this inquiry to price" in r.get_data(as_text=True)
    assert not _dpos()
    r = _post(clean, "/po/create?noboq=1", _base(project_id="gone"),
              [("Gauge", "1", "Nos")])
    assert "project no longer exists" in r.get_data(as_text=True)
    assert not _dpos()


def test_an_extra_needs_a_quantity_above_zero_and_comes_back_as_typed(clean):
    r = _post(clean, "/po/create?noboq=1", _base(), [("Strainer", "0", "Nos")])
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and "must be above 0" in page
    assert 'value="Strainer"' in page
    assert not _dpos()


# ── Extra items on a BOQ inquiry ────────────────────────────────────────────

def _boq_form(lines, **over):
    import json
    d = {"date": "2026-11-17", "vendor_id": VENDOR_ID, "notes": "",
         "xi_present": "1",
         "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "",
                                           "pcs": ""} for li in lines]})}
    d.update(over)
    return d


def test_extras_ride_after_the_boq_lines_and_the_library_is_not_written(shop, client):
    pick, _rate, name = _spec_pick()
    specs_before = copy.deepcopy(STORE.get("specs"))
    picked = shop["lines"][:2]
    r = _post(client, f"/po/create?boq={shop['boq']}", _boq_form(picked),
              [("", "3", "", pick), ("Typed gasket", "5", "Nos")])
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    po = next(iter(_dpos().values()))
    rows = [x for x in po["items"] if not x.get("is_header")]
    assert [x.get("line_id") for x in rows[:2]] == [li["line_id"] for li in picked]
    assert rows[2]["extra"] and rows[2]["line_id"] is None
    assert rows[2]["description"] == name and rows[2]["source"] == "spec"
    assert rows[3]["description"] == "Typed gasket" and rows[3]["source"] == "typed"
    assert STORE.get("specs") == specs_before
    pr = client.get(f"/po/print/{po['id']}").get_data(as_text=True)
    assert pr.index(picked[1]["description"][:20]) < pr.index("Typed gasket")


def test_a_boq_inquiry_may_tick_nothing_when_it_has_an_extra(shop, client):
    r = _post(client, f"/po/create?boq={shop['boq']}", _boq_form([]),
              [("Only an extra", "1", "Nos")])
    assert r.status_code == 302
    po = next(iter(_dpos().values()))
    assert po["boq_id"] == shop["boq"] and [x["description"] for x in po["items"]] == ["Only an extra"]
    # And with neither, it is still refused.
    r = _post(client, f"/po/create?boq={shop['boq']}", _boq_form([]), [])
    assert r.status_code == 200 and "No lines are ticked" in r.get_data(as_text=True)


def test_extras_are_added_and_kept_on_edit(shop, client):
    picked = shop["lines"][:1]
    assert _post(client, f"/po/create?boq={shop['boq']}", _boq_form(picked)).status_code == 302
    po = next(iter(_dpos().values()))
    edit = client.get(f"/po/edit/{po['id']}").get_data(as_text=True)
    assert 'name="xi_desc"' in edit
    lid = po["items"][-1]["line_id"]
    body = list({"date": "2026-11-18", "vendor_id": VENDOR_ID, "notes": "",
                 "delivery_to": "", "it_rows": "1", "xi_present": "1",
                 "doc_no_seq": po["ref"].rsplit("/", 1)[1]}.items())
    body += [("it_line_id", lid), ("it_kind", "item"), ("it_item_no", "1"),
             ("it_desc", po["items"][-1]["description"]), ("it_unit", "Nos"),
             ("it_qty", "2"), ("it_pcs", ""), ("it_make", ""), ("it_hsn", ""),
             ("it_image", "")]
    r = client.post(f"/po/edit/{po['id']}",
                    data=MultiDict(body + _extras(("Edit extra", "7", "Mtr"))))
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert po["items"][0]["line_id"] == lid
    assert po["items"][-1]["description"] == "Edit extra" and po["items"][-1]["extra"]
    # A stale tab (no markers at all) leaves every line, extras included.
    r = client.post(f"/po/edit/{po['id']}", data={
        "date": "2026-11-18", "vendor_id": VENDOR_ID,
        "doc_no_seq": po["ref"].rsplit("/", 1)[1]})
    assert r.status_code == 302
    assert po["items"][-1]["description"] == "Edit extra"
    # The edit form draws the stored extra in its own section, not the repeater.
    edit = client.get(f"/po/edit/{po['id']}").get_data(as_text=True)
    assert 'name="xi_desc" value="Edit extra"' in edit


def test_an_extra_takes_a_picture_on_the_pictures_page(clean):
    _post(clean, "/po/create?noboq=1", _base(), [("Valve", "1", "Nos")])
    po = next(iter(_dpos().values()))
    page = clean.get(f"/po/pictures/{po['id']}").get_data(as_text=True)
    assert 'value="it:0"' in page and "Valve" in page


# ── Convert to Purchase Order ───────────────────────────────────────────────

def _convert_body(**over):
    d = {"date": "2026-11-18", "vendor_id": VENDOR_ID, "status": "Draft",
         "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18"}
    d.update(over)
    return d


def test_a_no_boq_inquiry_converts_into_extra_lines(clean):
    import address
    address.ensure_demo_addresses()
    pick, rate, name = _spec_pick()
    _post(clean, "/po/create?noboq=1", _base(project_id=PID),
          [("", "4", "", pick, "Kirloskar"), ("Typed bracket", "6", "Nos")])
    did, po = next(iter(_dpos().items()))

    form = clean.get(f"/purchase/from-draft/{did}").get_data(as_text=True)
    assert "raised without a bill of quantities" in form
    assert f'value="{rate:.2f}"' in form, "the library's supply base rate did not prefill"
    assert 'value="Typed bracket"' in form

    r = clean.post(f"/purchase/from-draft/{did}", data=MultiDict(list(_convert_body().items()) + [
        ("extra_desc", name[:200]), ("extra_make", "Kirloskar"), ("extra_hsn", ""),
        ("extra_unit", po["items"][0]["unit"]), ("extra_qty", "4"),
        ("extra_rate", f"{rate:.2f}"), ("extra_discount", ""), ("extra_image", ""),
        ("extra_desc", "Typed bracket"), ("extra_make", ""), ("extra_hsn", ""),
        ("extra_unit", "Nos"), ("extra_qty", "6"), ("extra_rate", ""),
        ("extra_discount", ""), ("extra_image", "")]))
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    order = next(iter(STORE["purchases"].values()))
    assert not [x for x in order.get("line_items") or [] if not x.get("is_header")]
    xl = order["extra_lines"]
    assert [x["description"] for x in xl] == [name[:200], "Typed bracket"]
    assert xl[0]["rate"] == pytest.approx(rate) and xl[0]["qty"] == 4.0
    assert xl[0]["make"] == "Kirloskar"
    assert order["project_id"] == PID
    assert po["converted_po_ids"] == [order["id"]]


def test_a_boq_inquirys_extras_convert_and_its_boq_lines_convert_as_before(shop, client):
    picked = shop["lines"][:2]
    _post(client, f"/po/create?boq={shop['boq']}", _boq_form(picked),
          [("Unscheduled coupling", "3", "Nos")])
    did = next(iter(_dpos()))
    form = client.get(f"/purchase/from-draft/{did}").get_data(as_text=True)
    # The extra is in the extra-line repeater, NOT among the BOQ rows.
    assert form.count('name="dl_line_id"') == 2
    assert 'value="Unscheduled coupling"' in form

    r = client.post(f"/purchase/from-draft/{did}", data=MultiDict(list(_convert_body().items()) + [
        ("dl_line_id", picked[0]["line_id"]), ("dl_line_id", picked[1]["line_id"]),
        ("dl_qty", "2"), ("dl_qty", "3"), ("dl_rate", ""), ("dl_rate", ""),
        ("extra_desc", "Unscheduled coupling"), ("extra_make", ""), ("extra_hsn", ""),
        ("extra_unit", "Nos"), ("extra_qty", "3"), ("extra_rate", "55"),
        ("extra_discount", ""), ("extra_image", "")]))
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    order = next(iter(STORE["purchases"].values()))
    rows = [x for x in order["line_items"] if not x.get("is_header")]
    assert [x["line_id"] for x in rows] == [li["line_id"] for li in picked]
    assert rows[0]["price"] == float(picked[0]["supply_base_rate"])
    assert [x["description"] for x in order["extra_lines"]] == ["Unscheduled coupling"]
    assert order["extra_lines"][0]["rate"] == 55.0


def test_a_boq_only_inquiry_converts_with_a_blank_extra_repeater(shop, client):
    """No extras → the conversion form is what it always was (no prefill)."""
    import purchase
    picked = shop["lines"][:1]
    _post(client, f"/po/create?boq={shop['boq']}", _boq_form(picked))
    did = next(iter(_dpos()))
    assert purchase._draft_extra_prefill([]) == []
    form = client.get(f"/purchase/from-draft/{did}").get_data(as_text=True)
    assert "raised without a bill of quantities" not in form
    assert form.count('name="dl_line_id"') == 1


# ── The project page and the P&L ────────────────────────────────────────────

def test_a_no_boq_inquiry_shows_on_its_project_and_the_pnl_does_not_move(clean):
    before = pnl.project_pnl(PID)
    _post(clean, "/po/create?noboq=1", _base(project_id=PID),
          [("Pump set", "1", "Nos")])
    po = next(iter(_dpos().values()))
    page = clean.get(f"/projects/view/{PID}").get_data(as_text=True)
    assert f'/po/view/{po["id"]}' in page
    assert pnl.project_pnl(PID) == before, "an inquiry carries no money"
    # And an inquiry on no project is on no project's page.
    STORE["projects"]["p-other"] = dict(STORE["projects"][PID], id="p-other", name="Other")
    try:
        assert f'/po/view/{po["id"]}' not in clean.get("/projects/view/p-other").get_data(as_text=True)
    finally:
        STORE["projects"].pop("p-other", None)
