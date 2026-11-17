"""
The TAX INVOICE NUMBER as Tally Prime issued it
(17 November 2026, CLIENT_CHANGES.md §0 seventy-ninth block).

What this file holds:

  * an RA bill raised with a typed number carries it, in Tally's format, and
    prints it; blank still mints the automatic serial;
  * an ISSUED RA bill's number is changed on its edit-text page, a merged RA's
    on its edit page and a standalone tax invoice's on its edit page; a
    CANCELLED one stays locked;
  * a number already on another LIVE document carrying a TI number — tax
    invoice, RA bill or merged RA — is refused on create and on edit, naming
    it; trimmed and case-insensitive; a cancelled holder does not block;
  * every change appends {old, new, by, at}, shown on the view page and never
    printed; a per-login BLOCK of `docnum.override` still wins.
"""

import json

import pytest

import auth
import merged_ra
import tinum as TN
from store import STORE

from test_ra_record import boq_line, make_boq
from test_merged_ra import _bill, chain  # noqa: F401
from test_docnum import _ti_post, pi, store  # noqa: F401


def _schedule(bid="b1", qty=1000):
    line = boq_line("1", qty, s_rate=100.0)
    make_boq(bid, [line])
    return line["line_id"]


def _raise(client, bid, lid, qty=1, **form):
    before = set(STORE["ra_bills"])
    data = {"date": "2026-08-12",
            "ra_json": json.dumps({"lines": [{"line_id": lid, "qty": str(qty), "rate": "100"}]})}
    data.update(form)
    res = client.post(f"/ra/create?boq={bid}&leg=supply", data=data)
    return res, (STORE["ra_bills"][(set(STORE["ra_bills"]) - before).pop()]
                 if set(STORE["ra_bills"]) - before else None)


@pytest.fixture()
def clean(client):
    for key in ("boqs", "ra_bills", "merged_ras", "invoices"):
        STORE.setdefault(key, {}).clear()
    STORE["_boq_seeded"] = False
    yield client
    for key in ("ra_bills", "merged_ras", "invoices"):
        STORE[key].clear()


def _ti(tid, ref, status=""):
    STORE.setdefault("invoices", {})[tid] = {"id": tid, "ref": ref, "fy": "26-27",
                                             "date": "2026-08-20", "status": status}


def _edit_text(client, bill, number, **over):
    data = {k: str(bill.get(k) or "") for k, _l in __import__("ra").TEXT_FIELDS}
    data.update({TN.FIELD: number}, **over)
    return client.post(f"/ra/edit-text/{bill['id']}", data=data)


# ── RA bill ─────────────────────────────────────────────────────────────────

def test_an_ra_bill_raised_with_a_typed_tally_number_prints_it(clean):
    lid = _schedule()
    html = clean.get("/ra/create?boq=b1&leg=supply").get_data(as_text=True)
    assert f'name="{TN.FIELD}"' in html
    res, bill = _raise(clean, "b1", lid, **{TN.FIELD: "  SF-3 "})
    assert res.status_code == 302, res.get_data(as_text=True)[:800]
    assert bill["tax_invoice_ref"] == "SF-3", "trimmed, in Tally's own format"
    pr = clean.get(f"/ra/print/{bill['id']}").get_data(as_text=True)
    assert "SF-3" in pr
    # Blank still mints the automatic serial.
    _res, other = _raise(clean, "b1", lid)
    assert other["tax_invoice_ref"].startswith("SF/RI/")


def test_an_issued_ra_bills_number_is_corrected_with_history(clean):
    lid = _schedule()
    _res, bill = _raise(clean, "b1", lid)
    bill["status"] = "issued"
    was = bill["tax_invoice_ref"]
    form = clean.get(f"/ra/edit-text/{bill['id']}").get_data(as_text=True)
    assert f'name="{TN.FIELD}"' in form and was in form
    r = _edit_text(clean, bill, "125/26-27")
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert bill["tax_invoice_ref"] == "125/26-27"
    [h] = bill[TN.HISTORY_KEY]
    assert (h["old"], h["new"]) == (was, "125/26-27") and h["by"] in STORE["users"] and h["at"]
    view = clean.get(f"/ra/view/{bill['id']}").get_data(as_text=True)
    assert "Tax invoice number changes" in view
    pr = clean.get(f"/ra/print/{bill['id']}").get_data(as_text=True)
    assert "125/26-27" in pr and was not in pr
    assert "Tax invoice number changes" not in pr, "history is never printed"
    # Blank on an issued bill is refused; the number stays.
    r = _edit_text(clean, bill, "  ")
    assert r.status_code == 200 and bill["tax_invoice_ref"] == "125/26-27"


def test_a_draft_ra_bills_number_is_set_on_its_edit_form(clean):
    lid = _schedule()
    _res, bill = _raise(clean, "b1", lid)
    assert bill["status"] == "draft"
    form = clean.get(f"/ra/edit/{bill['id']}").get_data(as_text=True)
    assert f'name="{TN.FIELD}"' in form
    r = clean.post(f"/ra/edit/{bill['id']}", data={
        "date": "2026-08-12", "ra_no_typed": str(bill["ra_no"]), TN.FIELD: "SF-7",
        "ra_json": json.dumps({"lines": [{"line_id": lid, "qty": "1", "rate": "100"}]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert bill["tax_invoice_ref"] == "SF-7" and len(bill[TN.HISTORY_KEY]) == 1


def test_a_cancelled_ra_bill_stays_locked(clean):
    lid = _schedule()
    _res, bill = _raise(clean, "b1", lid, **{TN.FIELD: "SF-11"})
    bill["status"] = "cancelled"
    r = _edit_text(clean, bill, "SF-12")
    assert r.status_code == 302 and bill["tax_invoice_ref"] == "SF-11"
    assert TN.HISTORY_KEY not in bill


# ── Duplicates, across all three collections ────────────────────────────────

def test_a_number_on_a_tax_invoice_is_refused_on_an_ra_bill(clean):
    lid = _schedule()
    _ti("t1", "SF-3")
    res, bill = _raise(clean, "b1", lid, **{TN.FIELD: " sf-3 "})
    assert res.status_code == 200 and bill is None
    page = res.get_data(as_text=True)
    assert "already on Tax invoice SF-3" in page
    # A CANCELLED holder does not block.
    STORE["invoices"]["t1"]["status"] = "cancelled"
    res, bill = _raise(clean, "b1", lid, **{TN.FIELD: "SF-3"})
    assert res.status_code == 302 and bill["tax_invoice_ref"] == "SF-3"


def test_an_edit_onto_another_live_documents_number_is_refused(clean):
    lid = _schedule()
    _res, a = _raise(clean, "b1", lid, **{TN.FIELD: "SF-20"})
    _res, b = _raise(clean, "b1", lid, **{TN.FIELD: "SF-21"})
    b["status"] = "issued"
    r = _edit_text(clean, b, "Sf-20")
    assert r.status_code == 200 and b["tax_invoice_ref"] == "SF-21"
    assert f"RA{a['ra_no']}" in r.get_data(as_text=True)
    assert TN.HISTORY_KEY not in b
    # Saving its own number unchanged is fine.
    assert _edit_text(clean, b, "SF-21").status_code == 302


# ── Merged RA ───────────────────────────────────────────────────────────────

def test_a_merged_ras_number_is_corrected_and_cancelled_is_locked(chain, client):
    s = _bill(chain, "m-s", 1, "supply", "SF/RA/26-27/0001")
    i = _bill(chain, "m-i", 2, "installation", "SF/RA/26-27/0002")
    doc, err = merged_ra.create(s, i)
    assert doc, err
    form = client.get(f"/merged/edit/{doc['id']}").get_data(as_text=True)
    assert f'name="{TN.FIELD}"' in form
    data = {k: str(doc.get(k) or "") for k, _l in merged_ra.TEXT_FIELDS}
    data[TN.FIELD] = "SF-40"
    r = client.post(f"/merged/edit/{doc['id']}", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert doc["tax_invoice_ref"] == "SF-40" and len(doc[TN.HISTORY_KEY]) == 1
    pr = client.get(f"/merged/print/{doc['id']}").get_data(as_text=True)
    assert "SF-40" in pr and "Tax invoice number changes" not in pr
    # The legs of a live merge are offered no box of their own.
    s["status"] = "issued"
    assert f'name="{TN.FIELD}"' not in client.get(f"/ra/edit-text/{s['id']}").get_data(as_text=True)
    # A TI may not take the merged document's number.
    _ti("t9", "PLACEHOLDER")
    assert TN.holder_of("sf-40") == "Merged RA SF-40"
    doc["status"] = "cancelled"
    data[TN.FIELD] = "SF-41"
    client.post(f"/merged/edit/{doc['id']}", data=data)
    assert doc["tax_invoice_ref"] == "SF-40"


# ── Standalone tax invoice ──────────────────────────────────────────────────

def test_a_tax_invoice_takes_tallys_number_on_create_and_edit(store, pi):
    html = store.get("/invoice/from/p1").get_data(as_text=True)
    assert f'name="{TN.FIELD}"' in html
    r = _ti_post(store, **{TN.FIELD: "SF-9"})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:800]
    ti = next(iter(STORE["invoices"].values()))
    assert ti["ref"] == "SF-9"
    sheet = store.get(f"/invoice/view/{ti['id']}").get_data(as_text=True).split('class="doc-outer"')[1]
    assert "SF-9" in sheet
    # The automatic series was not spent: the next form still offers 0001.
    assert 'value="0001"' in store.get("/invoice/from/p1").get_data(as_text=True)
    # Issued → corrected on the edit page, with history.
    import lineedit as LE
    form = store.get(f"/invoice/edit/{ti['id']}").get_data(as_text=True)
    assert f'name="{TN.FIELD}"' in form and "locked" not in form.split(TN.FIELD)[1][:200]
    r = store.post(f"/invoice/edit/{ti['id']}", data={
        TN.FIELD: "125/26-27", "date": ti["date"],
        "place_of_supply": ti["place_of_supply"], "advance_received": "0",
        "tax_type": ti.get("tax_type", "exempt"), "to": ti.get("to", ""),
        LE.FIELD: json.dumps(LE.rows_for_form(ti["line_items"], 18.0))})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:800]
    assert ti["ref"] == "125/26-27" and ti[TN.HISTORY_KEY][0]["old"] == "SF-9"
    page = store.get(f"/invoice/view/{ti['id']}").get_data(as_text=True)
    screen, sheet = page.split('class="doc-outer"', 1)
    assert "125/26-27" in sheet and "SF-9" not in sheet, "the printed sheet carries the new number"
    assert "Tax invoice number changes" in screen and "Tax invoice number changes" not in sheet


def test_a_tax_invoice_may_not_take_an_ra_bills_number(store, pi):
    STORE["ra_bills"]["r1"] = {"id": "r1", "ref": "SF/RA/26-27/0001", "ra_no": 1,
                               "tax_invoice_ref": "SF-5", "status": "issued"}
    r = _ti_post(store, **{TN.FIELD: "sf-5"})
    assert r.status_code == 200 and not STORE["invoices"]
    assert "already on RA bill RA1" in r.get_data(as_text=True)


# ── Permission ──────────────────────────────────────────────────────────────

def test_a_login_blocked_from_docnum_override_cannot_change_it(clean):
    lid = _schedule()
    _res, bill = _raise(clean, "b1", lid, **{TN.FIELD: "SF-30"})
    bill["status"] = "issued"
    uid = "tn-director"
    STORE["users"][uid] = {"id": uid, "username": "d@test", "display_name": "D",
                           "password_hash": "x", "role_ids": ["role-director"],
                           "active": True, "created_at": "2026-08-01 09:00",
                           "created_by": "test", auth.PERM_DENY_FIELD: ["docnum.override"]}
    with clean.session_transaction() as sess:
        sess[auth.SESSION_KEY] = uid
    form = clean.get(f"/ra/edit-text/{bill['id']}").get_data(as_text=True)
    assert "readonly" in form.split(f'name="{TN.FIELD}"')[1][:200]
    r = _edit_text(clean, bill, "SF-31")
    assert r.status_code == 200 and bill["tax_invoice_ref"] == "SF-30"
