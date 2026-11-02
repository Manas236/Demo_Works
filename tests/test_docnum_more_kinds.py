"""
`docnum.py` extended to the rest of the numbered set — CLIENT_CHANGES.md §0
sixty-fourth block, Part 3 (31 Oct 2026): receipt, measurement sheet, work
order, product inquiry, and the BOQ's ROOT number in the scan. Forward only
everywhere: refused at or below the highest used in that series.
"""

import pytest

import docnum as DN
from store import STORE
from tests.test_entity_fallbacks import populated  # noqa: F401 — the fixture


@pytest.fixture()
def clean(client):
    for c in ("receipts", "measurements", "work_orders", "purchase_orders", "boqs"):
        STORE.setdefault(c, {}).clear()
    STORE.setdefault("settings", {}).pop(DN.HIGHWATER_RECORD, None)
    for rec in (DN.WO_SERIES_RECORD, DN.DPO_SERIES_RECORD):
        STORE["settings"].pop(rec, None)
    yield


@pytest.mark.parametrize("kind,coll,ref,fy", [
    (DN.RCPT, "receipts", "SF/RCPT/26-27/0004", "26-27"),
    (DN.MS, "measurements", "SF/MS/26-27/0004", "26-27"),
    (DN.WO, "work_orders", "WO/0004", ""),
    (DN.DPO, "purchase_orders", "SF/PO/0004", ""),
])
def test_forward_only_in_each_new_series(clean, kind, coll, ref, fy):
    STORE[coll]["x"] = {"id": "x", "ref": ref, "fy": fy}
    assert DN.highest_used(kind, fy) == 4
    _n, err = DN.validate(kind, fy, "4", 5, True)
    assert "highest already used in this series is 0004" in err
    _n, err = DN.validate(kind, fy, "3", 5, True)
    assert err
    n, err = DN.validate(kind, fy, "9", 5, True)
    assert (n, err) == (9, "")


def test_a_counter_series_counts_its_stored_counter(clean):
    STORE["settings"][DN.WO_SERIES_RECORD] = {"prefix": "WO", "next_no": "21"}
    assert DN.highest_used(DN.WO, "") == 20
    STORE["settings"][DN.DPO_SERIES_RECORD] = {"prefix": "SF/PO", "next_no": "8"}
    assert DN.highest_used(DN.DPO, "") == 7


def test_a_boq_revision_suffix_is_never_read_as_the_number(clean):
    STORE["boqs"]["a"] = {"id": "a", "ref": "SF/BOQ/26-27/0019", "fy": "26-27"}
    STORE["boqs"]["b"] = {"id": "b", "ref": "SF/BOQ/26-27/0019/3", "fy": "26-27",
                          "supersedes": "a"}
    assert DN.root_ordinal_of("SF/BOQ/26-27/0019/3") == 19
    assert DN.highest_used(DN.BOQ, "26-27") == 19


def test_the_work_order_create_takes_a_typed_number_and_the_counter_moves_past_it(clean, client):
    html = client.get("/wo/create").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html
    import settings as SET
    import workorder as WO
    assert WO._spend_ref(12).endswith("/0012")
    assert int(SET.wo_series()["next_no"]) == 13


def test_the_product_inquiry_counter_moves_past_a_typed_number(clean, client):
    import po_draft as DPO
    import settings as SET
    assert DPO._spend_ref(30).endswith("/0030")
    assert int(SET.po_series()["next_no"]) == 31


def test_the_receipt_and_sheet_forms_draw_the_field(clean, client):
    import demo_data as DD
    client.get("/boq/")
    html = client.get(f"/measurement/create?boq={DD.BOQ_META['id']}").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html and "Sheet No." in html


def test_a_receipt_saves_a_typed_forward_number_and_refuses_a_low_one(client, populated):
    STORE.setdefault("settings", {}).pop(DN.HIGHWATER_RECORD, None)
    html = client.get("/receipt/new?ra=r1-supply").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html and "Receipt No." in html
    form = {"date": "2026-08-10", "amount": "1", "mode": "neft"}
    before = set(STORE["receipts"])
    r = client.post("/receipt/new?ra=r1-supply", data=dict(form, doc_no_seq="0001"))
    assert r.status_code == 200 and "not available" in r.get_data(as_text=True)
    assert set(STORE["receipts"]) == before
    r = client.post("/receipt/new?ra=r1-supply", data=dict(form, doc_no_seq="0040"))
    assert r.status_code == 302
    new = [v for k, v in STORE["receipts"].items() if k not in before][0]
    assert new["ref"] == "SF/RCPT/26-27/0040"
    assert new["number_override"]["to"] == "SF/RCPT/26-27/0040"
