"""
A proforma invoice with NO BOQ and NO quotation — `/proforma/new`
(17 November 2026, CLIENT_CHANGES.md §0 seventy-fifth block).

The figures are `lineedit.tax_figures()` — the arithmetic `/proforma/edit`
already prices a PI with — so the property tested here is that the new path
writes a PI whose stored figures are exactly what that function returns for
the same lines, in the ONE PI series, and that it prints like any other PI.
"""

import json

import pytest

import buypick as BYP
import lineedit as LE
import roundoff as RO
from store import STORE


def _lines(*rows):
    return json.dumps([{"name": n, "part_no": "", "make": "", "hsn": "8424",
                        "qty": q, "unit": "Nos", "price": r, "discount_pct": "",
                        "gst_rate": "18", "is_header": False} for n, q, r in rows])


def _form(**over):
    data = {"date": "2026-11-17", "advance_pct": "100", "tax_type": "cgst_sgst",
            "account_name": "Acme Builders", "to": "Acme Builders\nPune",
            "ship_same": "1", RO.FIELD: "1", RO.MARK: "1",
            LE.FIELD: _lines(("Fire extinguisher 9 kg", "3", "2450.50"))}
    data.update(over)
    return data


@pytest.fixture()
def clean(client):
    STORE["proformas"].clear()
    yield client
    STORE["proformas"].clear()


def test_the_register_offers_a_new_pi_without_a_boq(clean):
    html = clean.get("/proforma/").get_data(as_text=True)
    assert 'href="/proforma/new"' in html and "New PI (no BOQ)" in html
    form = clean.get("/proforma/new")
    assert form.status_code == 200
    page = form.get_data(as_text=True)
    assert 'name="party_book_id"' in page and LE.FIELD in page


def test_a_no_boq_pi_is_priced_by_the_existing_arithmetic(clean):
    r = clean.post("/proforma/new", data=_form())
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    pi = next(iter(STORE["proformas"].values()))
    assert pi["quotation_id"] == "" and pi["boq_id"] == ""
    lines, err = LE.parse(_form()[LE.FIELD], [], default_gst=18.0)
    assert not err
    sub, tax, grand, ro, qty = LE.tax_figures(lines, "cgst_sgst", pi[RO.FIELD])
    assert (pi["subtotal"], pi["tax_info"], pi["grand_total"], pi["round_off"]) == (
        sub, tax, grand, ro)
    assert pi["amount_due"] == RO.apply(grand, pi[RO.FIELD])[0]
    assert pi["ref"].startswith("PI")
    # The register names it, and the view and the print render.
    assert "No BOQ" in clean.get("/proforma/").get_data(as_text=True)
    view = clean.get(f"/proforma/view/{pi['id']}")
    assert view.status_code == 200
    assert "Fire extinguisher 9 kg" in view.get_data(as_text=True)


def test_the_round_off_tick_is_honoured_both_ways(clean):
    on = clean.post("/proforma/new", data=_form())
    off = clean.post("/proforma/new", data={k: v for k, v in _form().items()
                                            if k != RO.FIELD})
    assert on.status_code == off.status_code == 302
    a, b = sorted(STORE["proformas"].values(), key=lambda p: p["ref"])
    assert RO.is_on(a, True) is True and RO.is_on(b, True) is False
    assert a["round_off"] != 0 or a["grand_total"] == round(a["grand_total"])
    assert b["round_off"] == 0


@pytest.mark.parametrize("over,needle", [
    ({LE.FIELD: "[]"}, "at least one priced line"),
    ({"account_name": "", "to": ""}, "Name the customer"),
    ({"advance_pct": "0"}, "Advance %"),
    ({"project_id": "gone"}, "project no longer exists"),
    ({"party_book_id": "gone"}, "no longer in the address book"),
])
def test_a_bad_form_is_refused_and_writes_nothing(clean, over, needle):
    r = clean.post("/proforma/new", data=_form(**over))
    assert r.status_code == 200 and needle in r.get_data(as_text=True)
    assert not STORE["proformas"]


def test_the_address_book_fills_only_the_blanks(clean):
    bid, book = next(iter((STORE.get("addresses") or {}).items()), (None, None))
    if not bid:
        pytest.skip("no address book in this store")
    r = clean.post("/proforma/new", data=_form(account_name="", to="",
                                               party_book_id=bid))
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    pi = next(iter(STORE["proformas"].values()))
    assert pi["account_name"] == (book.get("company") or book.get("contact_name") or "").strip()
    assert pi["to"]


def test_the_form_offers_the_specification_library_and_never_writes_it(clean):
    BYP.ensure_seeded()
    if not BYP.spec_entries():
        pytest.skip("no specification library in this store")
    before = json.dumps(STORE.get("specs"), sort_keys=True, default=str)
    page = clean.get("/proforma/new").get_data(as_text=True)
    assert BYP.SPEC_GROUP in page
    clean.post("/proforma/new", data=_form())
    assert json.dumps(STORE.get("specs"), sort_keys=True, default=str) == before
