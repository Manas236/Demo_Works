"""
SITC follow-ups — CLIENT_CHANGES.md §0 eighty-seventh block (23 Nov 2026).

4a. A PI or Tax Invoice raised from an SITC BOQ heads its leg "Supply +
    Installation (SITC)", not "SUPPLY". Amounts, tax and numbering unchanged;
    split / supply_only / installation_only output byte-identical.
4b. On a BOQ whose rate basis makes an RA action impossible, the action is
    drawn disabled with a one-line reason; the server refusal is unchanged.
"""

import json
import re

import pytest

import boq as BQ
import proforma as PF
from store import STORE
from test_boq_rate_basis import a_line, one_section, save


def _boq(client, basis, **rates):
    kw = dict(supply_rate="1000", install_rate="")
    kw.update(rates)
    return save(client, one_section(
        a_line(item_no="1", description="Pump", unit="Nos", total_qty="2", **kw)),
        rate_basis=basis)


def _picked(rec, qty=2):
    li = [l for l in rec["line_items"] if not l.get("is_header")][0]
    return [{"line_id": li["line_id"], "is_header": False, "item_no": "1",
             "description": "Pump", "unit": "Nos", "qty": qty}], li


def test_the_sitc_heading_reads_the_combined_track(client):
    rec = _boq(client, "sitc")
    picked, li = _picked(rec)
    rows, err = PF.boq_line_items(picked, rec, "supply")
    assert not err
    assert rows[0]["is_header"] and rows[0]["leg_band"] == "supply"
    assert rows[0]["name"] == "Supply + Installation (SITC)"
    assert rows[-1]["price"] == 1000.0 and rows[-1]["total"] == 2000.0


@pytest.mark.parametrize("basis,rates,leg,band", [
    ("split", dict(supply_rate="1000", install_rate="300"), "both", None),
    ("supply_only", dict(supply_rate="1000"), "supply", "SUPPLY"),
    ("installation_only", dict(supply_rate="", install_rate="300"),
     "installation", "INSTALLATION"),
])
def test_every_other_basis_is_unchanged(client, basis, rates, leg, band):
    rec = _boq(client, basis, **rates)
    picked, _ = _picked(rec)
    rows, err = PF.boq_line_items(picked, rec, leg)
    assert not err
    bands = [r["name"] for r in rows if r.get("leg_band")]
    assert bands == (["SUPPLY", "INSTALLATION"] if band is None else [band])
    # The same rows as a schedule carrying no basis key at all (pre-21 Nov).
    legacy = dict(rec)
    legacy.pop(BQ.RATE_BASIS_KEY, None)
    assert PF.boq_line_items(picked, legacy, leg) == (rows, err)


def _payload(li, q=2):
    return json.dumps({"lines": [{"line_id": li["line_id"], "qty": str(q)}]})


def test_a_pi_and_a_ti_from_an_sitc_boq_print_the_combined_heading(client):
    rec = _boq(client, "sitc")
    _, li = _picked(rec)
    r = client.post(f"/proforma/from-boq/{rec['id']}", data={
        "date": "2026-11-23", "advance_pct": "100", "validity_days": "15",
        "leg": "supply", "tax_type": "cgst_sgst", "pi_json": _payload(li)})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    pi = next(iter(STORE["proformas"].values()))
    assert pi["subtotal"] == 2000.0 and pi["tax_info"]["total"] == 360.0
    doc = client.get(f"/proforma/view/{pi['id']}").get_data(as_text=True)
    assert "<b>Supply + Installation (SITC)</b>" in doc
    assert "<b>SUPPLY</b>" not in doc
    r = client.post(f"/invoice/from-boq/{rec['id']}", data={
        "date": "2026-11-23", "place_of_supply": "Maharashtra",
        "advance_received": "0", "leg": "supply", "tax_type": "cgst_sgst",
        "ti_json": _payload(li)})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    ti = next(iter(STORE["invoices"].values()))
    assert ti["line_items"][0]["name"] == "Supply + Installation (SITC)"
    assert ti["subtotal"] == 2000.0


def _bar(client, rec):
    html = client.get(f"/boq/view/{rec['id']}").get_data(as_text=True)
    m = re.search(r'<div class="raise-bar">(.*?)</div>\n', html, re.S)
    assert m
    return m.group(1)


def _live(bar, label):
    return f'class="btn btn-ghost">&#43;&nbsp;{label}</a>' in bar


def _off(bar, label):
    return re.search(r'<span class="btn btn-ghost rb-off" aria-disabled="true" '
                     r'title="Not possible on this BOQ[^"]*">&#43;&nbsp;'
                     + re.escape(label) + "</span>", bar) is not None


def test_sitc_disables_installation_and_both_with_a_reason(client):
    bar = _bar(client, _boq(client, "sitc"))
    assert _live(bar, "RA &middot; Supply (SITC)")
    assert _off(bar, "RA &middot; Installation")
    assert _off(bar, "RA &middot; Supply &amp; Installation")
    assert "it carries no installation rate" in bar, "printed, not only a tooltip"


def test_supply_only_disables_installation_and_both(client):
    bar = _bar(client, _boq(client, "supply_only"))
    assert _live(bar, "RA &middot; Supply")
    assert _off(bar, "RA &middot; Installation")
    assert _off(bar, "RA &middot; Supply &amp; Installation")


def test_installation_only_disables_supply_and_both(client):
    bar = _bar(client, _boq(client, "installation_only",
                            supply_rate="", install_rate="300"))
    assert _off(bar, "RA &middot; Supply")
    assert _live(bar, "RA &middot; Installation")
    assert _off(bar, "RA &middot; Supply &amp; Installation")
    assert "it carries no supply rate" in bar


def test_split_draws_all_three_live(client):
    bar = _bar(client, _boq(client, "split", install_rate="300"))
    for label in ("RA &middot; Supply", "RA &middot; Installation",
                  "RA &middot; Supply &amp; Installation"):
        assert _live(bar, label), label
    assert "Not possible on this BOQ" not in bar


def test_the_server_still_refuses_the_typed_url(client):
    rec = _boq(client, "sitc")
    page = client.get(f"/ra/create?boq={rec['id']}&leg=installation").get_data(as_text=True)
    _, li = _picked(rec)
    assert f'id="q_{li["line_id"]}"' not in page, "nothing claimable — unchanged"
