"""
Every document raised FROM the BOQ, the three RA types, and one "For" at the
foot of the BOQ — CLIENT_CHANGES.md §0, fifty-first block (22 October 2026).

The client's words, relayed by Manas: *"every document could be raised from
BoQ only and RA especially all 3 types, Supply, Installation and then Supply
and Installation both"* — and, asked whether that took in the proforma,
*"proforma as well, when i said all i mean all, even TI"*. Separately: *"near
the bottom For Samruddhi is repeated twice once on left and once on right,
please remove the left one"*.

What this file holds to, and why each one is here rather than assumed:

1.  the BOQ sheet prints **"For <company>" once**, over the signatory, and a
    branch with an `&` in it is escaped once, not twice;
2.  `/boq/view` draws **all three RA types**, always — Supply, Installation and
    Supply & Installation (the MERGED RA) — and a type whose step is missing is
    a greyed chip with **no link** and a printed reason, never a link into a
    refusal;
3.  `/boq/view` draws **Proforma Invoice** and **Tax Invoice**, on the tip only,
    and only for somebody the gate would let through;
4.  a PI raised from a BOQ is the **ordinary PI** — `PI-nnnn`, its lines a
    snapshot at the schedule's SELLING rate, the supply HSN or the installation
    SAC, the clause heading above the sizes, both legs STACKED under a band
    each, the tax per slab;
5.  a TI raised from a BOQ is the **ordinary TI** — `SF/TI/yy-yy/nnnn`, the
    creator stamped, Rule 46's fields, and the RA bills already on the
    schedule NAMED on the form rather than silently ignored;
6.  a BOQ with a tax invoice under it **cannot be deleted** (cascade's hard
    stop), and the TI shows on the project's page;
7.  ⚠ a PI or TI with no BOQ behind it renders exactly as before —
    `tests/test_print_golden.py` holds that byte for byte, and its PI and TI
    goldens did not move.

⚠ No assertion here may pass against a blank page: each names a reference, a
  rate, a code or a link target that only appears when the feature worked.
"""

import json

import pytest

import approval
import boq as BQ
import branding as B
import cascade
import demo_data as DD
import pipeline as P
from store import STORE

from conftest import chain_ready


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def sched(client):
    """The seeded 97-line Sify schedule; its id."""
    client.get("/boq/")
    client.get("/settings/")
    return DD.BOQ_META["id"]


def _family(bid):
    """`(header, [child, child, child])` — the first clause and three sizes."""
    lines = STORE["boqs"][bid]["line_items"]
    heads = BQ.header_of(lines)
    first = min(heads)
    h = lines[heads[first]]
    kids = [lines[i] for i in sorted(heads) if heads[i] == heads[first]][:3]
    return h, kids


def _payload(*pairs):
    return json.dumps({"lines": [{"line_id": li["line_id"], "qty": str(q)}
                                 for li, q in pairs]})


def _pi_post(client, bid, payload, leg="supply", tax_type="cgst_sgst", **extra):
    form = {"date": "2026-10-22", "advance_pct": "100", "validity_days": "15",
            "leg": leg, "tax_type": tax_type, "pi_json": payload}
    form.update(extra)
    return client.post(f"/proforma/from-boq/{bid}", data=form)


def _ti_post(client, bid, payload, leg="supply", tax_type="cgst_sgst", **extra):
    form = {"date": "2026-10-22", "place_of_supply": "Karnataka",
            "advance_received": "0", "leg": leg, "tax_type": tax_type,
            "ti_json": payload}
    form.update(extra)
    return client.post(f"/invoice/from-boq/{bid}", data=form)


def _only(collection):
    recs = list(STORE[collection].values())
    assert len(recs) == 1, f"expected one {collection} record, found {len(recs)}"
    return recs[0]


def _issued_bill(bid, rid, leg, status="issued"):
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": f"SF/RA/26-27/{rid}", "ra_no": len(STORE["ra_bills"]) + 1,
        "boq_id": bid, "leg": leg, "status": status, "claims": [],
        "claim_subtotal": 0.0, "grand_total": 0.0,
    }


# ═══ 1. ONE "FOR" AT THE FOOT OF THE BOQ ════════════════════════════════════

def test_the_boq_sheet_says_for_the_company_once(client, sched):
    html = client.get(f"/boq/print/{sched}").get_data(as_text=True)
    sig = html[html.index('<div class="sig-block">'):]
    sig = sig[:sig.index("</td></tr></tbody>")]
    assert sig.count(">For ") == 1, sig
    assert f'<div class="sig-for">For {P.esc(B.COMPANY_NAME)}</div>' in sig
    assert "<b>For</b>" not in html, "the left-hand 'For' is back"


def test_the_signature_stays_on_the_right(client, sched):
    """The left cell is kept EMPTY — `.sig-block` is space-between."""
    html = client.get(f"/boq/print/{sched}").get_data(as_text=True)
    opener = '<div class="sig-block">'
    sig = html[html.index(opener) + len(opener):]
    assert sig.lstrip().startswith("<div></div>")


def test_a_branch_with_an_ampersand_is_escaped_once(client, sched):
    STORE["boqs"][sched]["company_branch"] = "Fire & Safety Branch"
    STORE["boqs"][sched]["auth_signatory"] = "R & D Head"
    html = client.get(f"/boq/print/{sched}").get_data(as_text=True)
    assert "For Fire &amp; Safety Branch" in html
    assert "R &amp; D Head" in html
    assert "&amp;amp;" not in html


# ═══ 2. THE THREE RA TYPES ON THE BOQ ═══════════════════════════════════════

def test_all_three_ra_types_are_drawn_on_a_fresh_schedule(client, sched):
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    for label in ("RA &middot; Supply</span>", "RA &middot; Installation</span>",
                  "RA &middot; Supply &amp; Installation</span>"):
        assert label in html, f"{label} is not drawn"
    assert html.count('class="btn btn-ghost rb-off"') == 3


def test_a_greyed_type_has_no_link_and_says_why(client, sched):
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert "/ra/create?boq=" not in html
    assert "/merged/create?boq=" not in html
    hint = html[html.index('class="rb-hint"'):]
    assert "Raise a delivery challan first" in hint
    assert "Raise a measurement sheet first" in hint
    assert "Needs an issued RA · Supply and an issued RA · Installation" in hint


def test_supply_and_installation_link_once_their_steps_exist(client, sched):
    chain_ready(sched)
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert f"/ra/create?boq={sched}&leg=supply" in html
    assert f"/ra/create?boq={sched}&leg=installation" in html
    assert "/merged/create?boq=" not in html, "nothing is issued yet to merge"
    assert html.count('class="btn btn-ghost rb-off"') == 1


def test_supply_and_installation_both_is_the_merged_ra(client, sched):
    chain_ready(sched)
    _issued_bill(sched, "s1", "supply")
    _issued_bill(sched, "i1", "installation")
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert f'href="/merged/create?boq={sched}"' in html
    assert 'class="btn btn-ghost rb-off"' not in html
    page = client.get(f"/merged/create?boq={sched}").get_data(as_text=True)
    assert "SF/RA/26-27/s1" in page and "SF/RA/26-27/i1" in page
    assert f'href="/boq/view/{sched}"' in page, "no way back to the schedule"


@pytest.mark.parametrize("status", ["draft", "cancelled"])
def test_a_draft_or_cancelled_bill_does_not_open_the_merge(client, sched, status):
    _issued_bill(sched, "s1", "supply")
    _issued_bill(sched, "i1", "installation", status=status)
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert "/merged/create?boq=" not in html


def test_a_greyed_chip_is_not_the_gate(client, sched):
    """The typed URL is still refused by `ra._c1_refusal()` — B5's rule."""
    r = client.get(f"/ra/create?boq={sched}&leg=supply", follow_redirects=False)
    assert r.status_code in (302, 303)


# ═══ 3. PROFORMA AND TAX INVOICE ON THE BOQ ═════════════════════════════════

def test_the_bar_offers_the_proforma_and_the_tax_invoice(client, sched):
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert f'href="/proforma/from-boq/{sched}"' in html
    assert f'href="/invoice/from-boq/{sched}"' in html
    for group in ("Purchase", "Site", "RA bills", "Invoices"):
        assert f'<span class="rb-lbl">{group}</span>' in html


def test_a_control_the_gate_would_refuse_is_not_drawn(client, sched, monkeypatch):
    import auth
    real = auth.can_reach
    monkeypatch.setattr(auth, "can_reach",
                        lambda ep, user=None: ep != "invoice.from_boq" and real(ep, user))
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert "/invoice/from-boq/" not in html
    assert f'href="/proforma/from-boq/{sched}"' in html


def test_a_superseded_schedule_offers_nothing_to_raise(client, sched):
    STORE["boqs"]["rev1"] = dict(STORE["boqs"][sched], id="rev1",
                                 ref="SF/BOQ/26-27/0099", supersedes=sched, rev_no=1)
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert 'class="raise-bar"' not in html
    assert "/proforma/from-boq/" not in html and "/invoice/from-boq/" not in html


@pytest.mark.parametrize("route", ["/proforma/from-boq", "/invoice/from-boq"])
def test_a_superseded_schedule_is_refused_at_the_route(client, sched, route):
    STORE["boqs"]["rev1"] = dict(STORE["boqs"][sched], id="rev1",
                                 ref="SF/BOQ/26-27/0099", supersedes=sched, rev_no=1)
    r = client.get(f"{route}/{sched}", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "superseded" in r.headers["Location"]


@pytest.mark.parametrize("route", ["/proforma/from-boq", "/invoice/from-boq"])
def test_an_unknown_schedule_is_refused(client, sched, route):
    r = client.get(f"{route}/no-such-boq", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/boq/" in r.headers["Location"]


# ═══ 4. THE PROFORMA RAISED FROM A BOQ ═════════════════════════════════════

def test_the_proforma_form_renders_the_schedule(client, sched):
    h, kids = _family(sched)
    html = client.get(f"/proforma/from-boq/{sched}").get_data(as_text=True)
    assert "SF/BOQ/26-27/0001" in html
    assert f'id="c_{kids[0]["line_id"]}"' in html
    assert 'name="leg" value="supply" checked' in html
    assert 'name="leg" value="both"' in html
    assert "The invoice will be numbered PI-" in html


def test_a_supply_proforma_carries_the_supply_rate_and_hsn(client, sched):
    h, kids = _family(sched)
    r = _pi_post(client, sched, _payload((kids[0], 4), (kids[1], 12)))
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:2000]
    pi = _only("proformas")
    assert pi["ref"].startswith("PI-")
    assert pi["boq_id"] == sched and pi["boq_ref"] == "SF/BOQ/26-27/0001"
    assert pi["boq_leg"] == "supply" and pi["quotation_id"] == ""
    rows = pi["line_items"]
    assert rows[0]["is_header"] and rows[0]["leg_band"] == "supply"
    assert rows[1]["is_header"] and rows[1]["line_id"] == h["line_id"]
    priced = [r for r in rows if not r.get("is_header")]
    assert [r["line_id"] for r in priced] == [kids[0]["line_id"], kids[1]["line_id"]]
    assert priced[0]["price"] == kids[0]["supply_rate"]
    assert priced[0]["hsn"] == kids[0]["supply_hsn"]
    assert priced[0]["total"] == round(4 * kids[0]["supply_rate"], 2)
    sub = round(4 * kids[0]["supply_rate"] + 12 * kids[1]["supply_rate"], 2)
    assert pi["subtotal"] == sub
    assert pi["tax_info"]["cgst_rate"] == 9.0
    assert pi["tax_info"]["total"] == round(2 * round(sub * 0.09, 2), 2)
    assert pi["grand_total"] == round(sub + pi["tax_info"]["total"], 2)
    assert pi["amount_due"] == pi["grand_total"] and pi["balance_due"] == 0.0


def test_an_installation_proforma_carries_the_sac(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)), leg="installation")
    priced = [r for r in _only("proformas")["line_items"] if not r.get("is_header")]
    assert priced[0]["price"] == kids[0]["install_rate"]
    assert priced[0]["hsn"] == kids[0]["install_sac"]
    assert priced[0]["leg"] == "installation"


def test_both_legs_are_stacked_supply_first_under_a_band_each(client, sched):
    h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4), (kids[1], 2)), leg="both")
    rows = _only("proformas")["line_items"]
    bands = [r["leg_band"] for r in rows if r.get("leg_band")]
    assert bands == ["supply", "installation"]
    legs = [r["leg"] for r in rows if not r.get("is_header")]
    assert legs == ["supply", "supply", "installation", "installation"]
    # The clause heading prints once under EACH band.
    assert sum(1 for r in rows if r.get("line_id") == h["line_id"]) == 2


def test_a_lowered_quantity_is_what_is_invoiced(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 1.5)))
    priced = [r for r in _only("proformas")["line_items"] if not r.get("is_header")]
    assert priced[0]["qty"] == 1.5


def test_nothing_ticked_writes_nothing(client, sched):
    r = _pi_post(client, sched, json.dumps({"lines": []}))
    assert r.status_code == 200
    assert "No lines are ticked" in r.get_data(as_text=True)
    assert not STORE["proformas"]


def test_a_leg_the_ticked_lines_are_not_priced_for_is_refused(client, sched):
    _h, kids = _family(sched)
    kids[0]["install_rate"] = 0.0          # the STORE's own line — not a copy
    r = _pi_post(client, sched, _payload((kids[0], 4)), leg="installation")
    assert r.status_code == 200
    assert "nothing to invoice" in r.get_data(as_text=True)
    assert not STORE["proformas"]


def test_a_refused_post_keeps_what_was_ticked(client, sched):
    _h, kids = _family(sched)
    r = _pi_post(client, sched, _payload((kids[1], 7.25)), date="")
    html = r.get_data(as_text=True)
    assert "Invoice date is required." in html
    assert f'id="c_{kids[0]["line_id"]}"' in html
    assert f'id="c_{kids[0]["line_id"]}" checked' not in html
    assert f'id="c_{kids[1]["line_id"]}" checked' in html
    assert 'value="7.25"' in html


def test_two_gst_rates_print_one_tax_row_per_slab(client, sched):
    _h, kids = _family(sched)
    kids[1]["supply_gst_rate"] = 12.0      # the STORE's own line — not a copy
    _pi_post(client, sched, _payload((kids[0], 4), (kids[1], 12)))
    pi = _only("proformas")
    ti = pi["tax_info"]
    assert "cgst_rate" not in ti
    a = round(4 * kids[0]["supply_rate"] * 0.09, 2)
    b = round(12 * kids[1]["supply_rate"] * 0.06, 2)
    assert ti["CGST @ 9%"] == a and ti["SGST @ 9%"] == a
    assert ti["CGST @ 6%"] == b and ti["SGST @ 6%"] == b
    assert ti["total"] == round(2 * a + 2 * b, 2)
    html = client.get(f"/proforma/view/{pi['id']}").get_data(as_text=True)
    assert "CGST @ 6%" in html and "CGST @ 9%" in html


def test_the_igst_head_is_honoured(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)), tax_type="igst")
    ti = _only("proformas")["tax_info"]
    assert ti["igst_rate"] == 18.0 and "CGST" not in ti
    assert ti["IGST"] == round(4 * kids[0]["supply_rate"] * 0.18, 2)


def test_the_printed_proforma_names_the_boq_and_numbers_only_lines(client, sched):
    h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4), (kids[1], 12)))
    pi = _only("proformas")
    html = client.get(f"/proforma/view/{pi['id']}").get_data(as_text=True)
    assert "Against BOQ" in html and "SF/BOQ/26-27/0001" in html
    assert "against Bill of Quantities SF/BOQ/26-27/0001" in html
    assert "raised against our Bill of Quantities SF/BOQ/26-27/0001" in html
    assert "<b>SUPPLY</b>" in html
    assert P.esc(h["description"]) in html
    assert '<td class="c-sno">1</td>' in html and '<td class="c-sno">2</td>' in html
    assert '<td class="c-sno">3</td>' not in html, "a heading row was numbered"
    assert f'href="/boq/view/{sched}"' in html


def test_the_register_links_a_boq_proforma_to_its_schedule(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)))
    html = client.get("/proforma/").get_data(as_text=True)
    assert f'href="/boq/view/{sched}" class="btn-view">BOQ SF/BOQ/26-27/0001' in html


def test_the_pictures_page_offers_lines_not_headings(client, sched):
    h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)))
    pi = _only("proformas")
    html = client.get(f"/proforma/pictures/{pi['id']}").get_data(as_text=True)
    assert P.esc(kids[0]["description"].split()[0]) in html
    assert "SUPPLY" not in html


def test_the_boq_lists_the_proforma_raised_from_it(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)))
    pi = _only("proformas")
    html = client.get(f"/boq/view/{sched}").get_data(as_text=True)
    assert "Proforma &amp; tax invoices raised" in html
    assert f'href="/proforma/view/{pi["id"]}">{pi["ref"]}' in html


def test_a_tax_invoice_off_a_boq_proforma_carries_the_schedule(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)))
    pi = _only("proformas")
    form = client.get(f"/invoice/from/{pi['id']}").get_data(as_text=True)
    assert '<option  selected>Karnataka</option>' in form, \
        "the place of supply did not default to the schedule's State"
    r = client.post(f"/invoice/from/{pi['id']}",
                    data={"date": "2026-10-23", "place_of_supply": "Karnataka",
                          "advance_received": "0"})
    assert r.status_code in (302, 303)
    ti = _only("invoices")
    assert ti["boq_ref"] == "SF/BOQ/26-27/0001" and ti["proforma_id"] == pi["id"]
    assert [r["line_id"] for r in ti["line_items"]] == \
        [r["line_id"] for r in pi["line_items"]]
    html = client.get(f"/invoice/view/{ti['id']}").get_data(as_text=True)
    assert "Against BOQ" in html
    assert (f"Supplied against our Proforma Invoice {pi['ref']} dated 2026-10-22, "
            f"raised on our Bill of Quantities SF/BOQ/26-27/0001") in html


# ═══ 5. THE TAX INVOICE RAISED FROM A BOQ ══════════════════════════════════

def test_the_tax_invoice_is_the_ordinary_one(client, sched):
    h, kids = _family(sched)
    r = _ti_post(client, sched, _payload((kids[0], 4)), leg="both")
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:2000]
    ti = _only("invoices")
    assert ti["ref"] == "SF/TI/26-27/0001" and ti["fy"] == "26-27"
    assert ti["boq_id"] == sched and ti["boq_leg"] == "both"
    assert ti["proforma_id"] == "" and ti["quotation_id"] == ""
    assert ti["place_of_supply"] == "Karnataka" and ti["pos_code"] == "29"
    assert ti["created_by"]
    assert ti.get(approval.RAISED_WHILE_OFF_FIELD) is True
    legs = [r["leg"] for r in ti["line_items"] if not r.get("is_header")]
    assert legs == ["supply", "installation"]
    assert ti["net_payable"] == ti["grand_total"]


def test_the_series_runs_on_from_an_invoice_raised_off_a_proforma(client, sched):
    _h, kids = _family(sched)
    STORE["invoices"]["old"] = {"id": "old", "ref": "SF/TI/26-27/0004", "fy": "26-27"}
    _ti_post(client, sched, _payload((kids[0], 4)))
    refs = sorted(t["ref"] for t in STORE["invoices"].values())
    assert refs == ["SF/TI/26-27/0004", "SF/TI/26-27/0005"]


def test_the_printed_tax_invoice_prints_headings_without_an_hsn_chip(client, sched):
    h, kids = _family(sched)
    _ti_post(client, sched, _payload((kids[0], 4)))
    ti = _only("invoices")
    html = client.get(f"/invoice/view/{ti['id']}").get_data(as_text=True)
    assert "TAX INVOICE" in html and ti["ref"] in html
    assert "Against BOQ" in html
    assert "Supplied against our Bill of Quantities SF/BOQ/26-27/0001" in html
    band = html[html.index("<b>SUPPLY</b>") - 400:html.index("<b>SUPPLY</b>") + 300]
    assert 'class="c-hsn"></td>' in band and "todo-chip" not in band
    assert kids[0]["supply_hsn"] in html
    assert f'href="/boq/view/{sched}"' in html


def test_place_of_supply_is_required(client, sched):
    _h, kids = _family(sched)
    r = _ti_post(client, sched, _payload((kids[0], 4)), place_of_supply="")
    assert "Place of supply is required" in r.get_data(as_text=True)
    assert not STORE["invoices"]


def test_an_advance_above_the_invoice_value_is_refused(client, sched):
    _h, kids = _family(sched)
    r = _ti_post(client, sched, _payload((kids[0], 1)), advance_received="99999999")
    assert "is more than the invoice value" in r.get_data(as_text=True)
    assert not STORE["invoices"]


def test_the_form_names_the_ra_bills_already_on_the_schedule(client, sched):
    _issued_bill(sched, "s1", "supply")
    _issued_bill(sched, "gone", "installation", status="cancelled")
    html = client.get(f"/invoice/from-boq/{sched}").get_data(as_text=True)
    assert "1 RA bill already claims on this schedule" in html
    assert "An RA bill is itself a tax invoice" in html
    assert "RA2" not in html, "a cancelled bill was counted"


def test_the_form_names_the_tax_invoices_already_raised(client, sched):
    _h, kids = _family(sched)
    _ti_post(client, sched, _payload((kids[0], 4)))
    ti = _only("invoices")
    html = client.get(f"/invoice/from-boq/{sched}").get_data(as_text=True)
    assert "Tax invoices already raised from this schedule" in html
    assert f'href="/invoice/view/{ti["id"]}">{ti["ref"]}' in html


def test_a_head_that_disagrees_with_the_place_of_supply_is_warned(client, sched,
                                                                  monkeypatch):
    """We supply from Maharashtra (27…); the schedule's site is Karnataka."""
    monkeypatch.setattr(B, "COMPANY_GSTIN", "27AAAAA0000A1Z5")
    html = client.get(f"/invoice/from-boq/{sched}").get_data(as_text=True)
    assert "Tax head may not match the place of supply" in html


def test_a_boq_with_a_tax_invoice_under_it_cannot_be_deleted(client, sched):
    _h, kids = _family(sched)
    _ti_post(client, sched, _payload((kids[0], 4)))
    report = cascade.impact_of("boqs", sched)
    assert report["blocked"] and report["blocked"]["collection"] == "invoices"


def test_a_boq_proforma_is_in_the_boq_delete_impact(client, sched):
    _h, kids = _family(sched)
    _pi_post(client, sched, _payload((kids[0], 4)))
    pi = _only("proformas")
    items = cascade.impact_of("boqs", sched)["items"]
    assert ("proformas", pi["id"]) in {(i["collection"], i["id"]) for i in items}


def test_the_tax_invoice_shows_on_the_projects_page(client, sched):
    STORE.setdefault("projects", {})["proj-x"] = {"id": "proj-x", "name": "Sify Phase II"}
    STORE["boqs"][sched]["project_id"] = "proj-x"
    _h, kids = _family(sched)
    _ti_post(client, sched, _payload((kids[0], 4)))
    ti = _only("invoices")
    assert ti["project_id"] == "proj-x"
    html = client.get("/projects/view/proj-x").get_data(as_text=True)
    assert ti["ref"] in html


def test_the_register_links_a_boq_invoice_to_its_schedule(client, sched):
    _h, kids = _family(sched)
    _ti_post(client, sched, _payload((kids[0], 4)))
    html = client.get("/invoice/").get_data(as_text=True)
    assert f'href="/boq/view/{sched}" class="btn-view">BOQ SF/BOQ/26-27/0001' in html


# ═══ 6. THE DROPDOWN THAT CARRIES A STORED VALUE ═══════════════════════════

def test_a_stored_term_reaches_the_dropdown_escaped(client, sched):
    STORE["boqs"][sched]["payment_terms"] = 'Advance <b>50%</b> & "rest"'
    html = client.get(f"/proforma/from-boq/{sched}").get_data(as_text=True)
    assert "Advance &lt;b&gt;50%&lt;/b&gt; &amp; &quot;rest&quot;" in html
    assert "<b>50%</b>" not in html


def test_a_listed_term_renders_byte_for_byte_as_before():
    import proforma
    import quotation
    for opts in (quotation._PAY_TERMS, quotation._DEL_TERMS, quotation._DISPATCH,
                 quotation._INCOTERMS, quotation._STATES_IN):
        cur = opts[1]
        assert (proforma._sel_keep("x", opts, cur)
                == quotation._sel_opts("x", opts, cur, cur))
