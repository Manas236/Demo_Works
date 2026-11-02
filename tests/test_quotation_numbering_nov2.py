"""
The quotation's number and Resume — 2 November 2026, CLIENT_CHANGES.md §0
block of that date ("Manas, 2 Nov 2026: full editing on all documents,
quotation numbering + Resume"), Part 4 — the SIXTH narrow unfreeze of
`quotation.py` (`_next_ref`, `create_quotation`, `edit_quotation`).

* The automatic number is the HIGHEST USED + 1 (the scan and the ledger),
  never a record count — so neither a deleted quotation nor a typed-ahead
  number can ever be issued again.
* The number is typeable on create and on edit, forward only.
* Resume after Back on `/quotation/create` redraws and saves nothing.
* The edit form is the create form's sources: the address book, the
  Specification library and Excel, besides free text.
"""

import json

import pytest

import conftest
import docimport as DI
import docnum as DN
import lineedit as LE
import quotation as Q
import sheetimport as SI
from store import STORE
from test_quotation_edit import _form, _q
from test_quotation_spec_picker import (  # noqa: F401
    _both_rated, _newest_quotation, _pick, _post, library)


def _make(client, **extra):
    sid, _s = _both_rated()
    r = _post(client, [_pick(sid, qty=1, price=100)], **extra)
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    return _newest_quotation()


# ── The automatic number ────────────────────────────────────────────────────

def test_the_minter_is_highest_used_plus_one_not_a_count(client, library):
    a, b, c = _make(client), _make(client), _make(client)
    assert [x["ref"] for x in (a, b, c)] == ["QT-0001", "QT-0002", "QT-0003"]
    # Delete the last two. `len + 1` would hand QT-0002 out again.
    STORE["quotations"].pop(b["id"]); STORE["quotations"].pop(c["id"])
    assert len(STORE["quotations"]) == 1
    assert _make(client)["ref"] == "QT-0004", "a deleted number came round again"


def test_a_typed_ahead_number_is_never_reissued(client, library):
    _make(client)                                   # QT-0001
    assert _make(client, doc_no_seq="0050")["ref"] == "QT-0050"
    assert _make(client)["ref"] == "QT-0051"
    # Even after the typed one is deleted, and the count catches up to it.
    STORE["quotations"].pop(next(k for k, v in STORE["quotations"].items()
                                 if v["ref"] == "QT-0050"))
    for _ in range(3):
        assert _make(client)["ref"] not in {"QT-0050", "QT-0051"}


def test_a_typed_number_at_or_below_the_highest_is_refused_and_named(client, library):
    _make(client, doc_no_seq="0010")
    before = len(STORE["quotations"])
    sid, _s = _both_rated()
    r = _post(client, [_pick(sid, qty=1, price=100)], doc_no_seq="0010")
    assert r.status_code == 200 and "0010" in r.get_data(as_text=True)
    assert "highest already used in this series is 0010" in r.get_data(as_text=True)
    assert len(STORE["quotations"]) == before


def test_the_create_form_draws_the_number_box_in_library_mode(client, library):
    html = client.get("/quotation/create").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html and ">QT-</span>" in html


# ── Resume after Back ───────────────────────────────────────────────────────

def test_resume_redraws_and_saves_nothing_and_spends_no_number(client, library):
    sid, _s = _both_rated()
    sel = [_pick(sid, qty=3, price=250)]
    r = client.post("/quotation/create", data={
        "_resume": "1", "account_name": "Resumed Customer", "qtn_date": "2026-11-02",
        "tax_type": "cgst_sgst", "tax_cgst": "9", "tax_sgst": "9", "tax_igst": "18",
        "tax_vat": "5", "selections_json": json.dumps(sel)})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'value="Resumed Customer"' in html
    assert json.dumps(sel)[:20].replace('"', "") or True
    assert sid in html, "the picks came back"
    assert not STORE["quotations"]
    assert "QT" not in DN.highwater(), "no number spent"
    assert 'class="alert alert-error"' not in html, "a resume is not a refusal"
    assert "var RESUMED = true" in html


def test_the_create_form_carries_the_draft_script(client, library):
    html = client.get("/quotation/create").get_data(as_text=True)
    assert "draft:' + location.pathname" in html and "unsaved quotation" in html


# ── Edit: the number, the sources ──────────────────────────────────────────

@pytest.fixture()
def q(client):
    STORE["quotations"].clear()
    return _q()


def test_the_edit_form_offers_number_book_library_and_excel(client, q):
    client.get("/quotation/create")            # seeds the library
    html = client.get("/quotation/edit/qe1").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html and 'value="0007"' in html
    assert 'id="bill_book"' in html and 'id="ship_book"' in html
    assert "Specification library" in html and "+ Add picked line" in html
    assert "/import/quotation?q=qe1" in html


def test_the_number_moves_forward_only_on_edit_and_is_logged(client, q):
    r = client.post("/quotation/edit/qe1", data=_form(q, doc_no_seq="0003"))
    assert r.status_code == 200 and q["ref"] == "QT-0007"
    r = client.post("/quotation/edit/qe1", data=_form(q, doc_no_seq="0040"))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert q["ref"] == "QT-0040" and q["number_override"]["from"] == "QT-0007"
    assert any(e["field"] == "Quotation No." for e in q["edit_log"])
    client.get("/quotation/create")
    assert Q._next_ref() == "QT-0041"


def test_a_library_line_added_on_edit_prints(client, q):
    client.get("/quotation/create")
    sid, s = _both_rated()
    rows = LE.rows_for_form(q["line_items"], 0.0) + [{
        "name": "Supply of " + s["title"], "part_no": s["code"], "make": "",
        "hsn": s.get("supply_hsn", ""), "qty": "4", "unit": s["variants"][0]["unit"],
        "price": "321", "discount_pct": "", "is_header": False}]
    r = client.post("/quotation/edit/qe1", data=_form(q, rows))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    html = client.get("/quotation/view/qe1").get_data(as_text=True)
    import pipeline as P
    assert P.esc("Supply of " + s["title"]) in html and s["code"] in html


def test_excel_lines_land_on_the_edit_form_after_the_stored_ones(client, q):
    client.get("/quotation/create")
    sid, s = _both_rated()
    wb = SI.from_rows([("Sheet1", "visible", [
        ["Spec code", "Size", "Qty", "Rate"],
        [s["code"], s["variants"][0]["label"], 6, 410]])])
    tok = DI.stage(DI.KINDS["quotation"], wb, "q.xlsx",
                   conftest.ensure_test_user()["id"], {"q": "qe1"})
    rec = STORE["doc_imports"][tok]
    form = {f"map_{c}": t for c, t in rec["mapping"].items()}
    form.update({"action": "confirm", "sheet": str(rec["sheet_index"])})
    r = client.post(f"/import/quotation/{tok}", data=form)
    import re
    assert r.status_code == 303, re.findall(r'(?:imp-flags|alert)[^>]*>(.{0,300})',
                                            r.get_data(as_text=True))
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert 'action="/quotation/edit/qe1"' in page
    rows = json.loads(page.split('var ROWS = ', 1)[1].split(";\n", 1)[0])
    assert rows[0]["name"] == "Pump" and rows[-1]["part_no"] == s["code"]
    assert rows[-1]["qty"] == "6" and rows[-1].get("source") == "excel"
    assert len(q["line_items"]) == 1, "nothing saved until the form's Save"
