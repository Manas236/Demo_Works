"""
The tax invoice generated from an RA bill, and a merged RA set's — TEXT
fields only after issue (CLIENT_CHANGES.md §0 sixty-fourth block, Part 2,
Manas, 31 Oct 2026). Quantity, rate and amount follow the RA bill and are not
on the form; the number is locked; every change is logged and the band is on
the screen page only.
"""

import copy

import editlog as EL
import ra as RA
from store import STORE
from tests.test_entity_fallbacks import populated  # noqa: F401 — the fixture


def _form(rec, fields, **over):
    d = {k: str(rec.get(k) or "") for k, _l in fields}
    d.update(over)
    return d


def test_an_issued_bills_invoice_text_is_edited_and_logged(client, populated):
    rid = "r1-supply"
    bill = STORE["ra_bills"][rid]
    claims_before = copy.deepcopy(bill.get("claims"))
    figures = {k: bill.get(k) for k in ("grand_total", "claim_subtotal", "tax_invoice_ref", "ref")}
    r = client.post(f"/ra/edit-text/{rid}", data=_form(
        bill, RA.TEXT_FIELDS, po_ref="PO/2026/77", bill_gstin="27ZZZZZ9999Z1Z5",
        # figures smuggled onto the form are never read
        grand_total="1", tax_invoice_ref="SF/TI/26-27/9999"))
    assert r.status_code == 302
    bill = STORE["ra_bills"][rid]
    assert bill["po_ref"] == "PO/2026/77" and bill["bill_gstin"] == "27ZZZZZ9999Z1Z5"
    assert bill["claims"] == claims_before
    assert {k: bill.get(k) for k in figures} == figures
    fields = {e["field"] for e in bill[EL.FIELD]}
    assert fields == {"Customer PO No.", "Customer GSTIN"}
    view = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "Edited after issue on" in view
    printed = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert "Edited after issue on" not in printed


def test_a_draft_or_cancelled_bill_is_refused(client, populated):
    draft = STORE["ra_bills"]["r2-supply"]
    assert client.get("/ra/edit-text/r2-supply").status_code == 302
    r = client.post("/ra/edit-text/r2-supply", data=_form(draft, RA.TEXT_FIELDS, notes="x"))
    assert r.status_code == 302 and EL.FIELD not in STORE["ra_bills"]["r2-supply"]
    STORE["ra_bills"]["r1-supply"]["status"] = "cancelled"
    r = client.post("/ra/edit-text/r1-supply",
                    data=_form(STORE["ra_bills"]["r1-supply"], RA.TEXT_FIELDS, notes="x"))
    assert r.status_code == 302 and EL.FIELD not in STORE["ra_bills"]["r1-supply"]


def test_the_dates_stay_in_the_numbers_year(client, populated):
    bill = STORE["ra_bills"]["r1-supply"]
    r = client.post("/ra/edit-text/r1-supply", data=_form(bill, RA.TEXT_FIELDS, date="2030-06-01"))
    assert r.status_code == 200 and "financial year" in r.get_data(as_text=True)


def test_the_merged_invoice_text_is_edited_and_logged(client, populated):
    import merged_ra as MR
    mid = next(iter(STORE["merged_ras"]))
    doc = STORE["merged_ras"][mid]
    totals = {k: doc.get(k) for k in ("grand_total", "tax_invoice_ref")}
    r = client.post(f"/merged/edit/{mid}", data=_form(doc, MR.TEXT_FIELDS,
                                                       contact_person="Mr Changed"))
    assert r.status_code == 302
    doc = STORE["merged_ras"][mid]
    assert doc["contact_person"] == "Mr Changed"
    assert {k: doc.get(k) for k in totals} == totals
    assert doc[EL.FIELD][-1]["field"] == "Contact person"
    assert "Edited after issue on" in client.get(f"/merged/view/{mid}").get_data(as_text=True)
    assert "Edited after issue on" not in client.get(f"/merged/print/{mid}").get_data(as_text=True)


def test_a_challan_edit_is_logged_and_banded_on_screen_only(client, populated):
    cid = next(iter(STORE["delivery_challans"]))
    dc = STORE["delivery_challans"][cid]
    form = {k: str(dc.get(k) or "") for k in ("date", "dispatch_mode", "dispatch_to",
                                               "po_no", "po_date", "notes", "consignee_id",
                                               "consignee_name", "consignee_addr",
                                               "consignee_phone")}
    form["po_no"] = "PO-CHANGED-1"
    r = client.post(f"/dc/edit/{cid}", data=form)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    log = STORE["delivery_challans"][cid][EL.FIELD]
    assert any(e["field"] == "PO No." and e["after"] == "PO-CHANGED-1" for e in log)
    assert "Edited after issue on" in client.get(f"/dc/view/{cid}").get_data(as_text=True)
    assert "Edited after issue on" not in client.get(f"/dc/print/{cid}").get_data(as_text=True)
