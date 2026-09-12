"""
A new quotation is written from the SPECIFICATION LIBRARY, not the catalogue.

11 September 2026, CLIENT_CHANGES.md §0, the twenty-seventh block: the
product catalogue is hidden from everybody (`tests/test_product_hidden.py`),
and `quotation.py` was unfrozen narrowly — for `_product_catalog_json()`,
`_process_selections()` and `create_quotation()` and nothing else — so the
picker on `/quotation/create` reads `STORE["specs"]`, the same library a BOQ
is written from. The freeze test in `tests/test_nav_user_chip.py` holds the
edit to those three functions.

⚠ **RETARGETED 12 September 2026 — SUPPLY ONLY** (CLIENT_CHANGES.md §0, the
twenty-eighth block, change 2). A quotation carries no installation leg: no
selector, no installation lines. This chain is quotation → proforma → tax
invoice for goods going out; installation is billed through BOQ → RA. Every
test below that exercised the installation leg is retargeted rather than
deleted — Installation is not offered, and a forged install-leg POST is
refused — and the two-leg mapping it replaces was, verbatim:

    picker    Spec → Size / variant → Leg → Qty
    name      "Supply of <title> — <variant>"  /  "Installation of <title> — <variant>"
    hsn       supply_hsn on a supply line, install_sac on an installation line

The mapping under test now:

    picker    Spec → Size / variant → Qty
    name      "Supply of <title> — <variant>"
    part_no   the spec code
    hsn       supply_hsn
    unit      the variant's unit
    price     the variant's default SUPPLY rate, SUGGESTED and editable

The picker also FOLLOWS the catalogue switch from the same date (change 1):
this file runs on the shipped configuration, the catalogue hidden, which is
the library picker. `tests/test_quotation_switch.py` covers the other mode.

and the four rules around it:

- one tax per quotation, NEVER auto-applied — the POST is refused, naming
  the lines and the rates, when the picked lines' library GST rates disagree
  with each other or with the Tax section (skipped for exempt / VAT);
- a leg with no library rate opens with an EMPTY price box, and a shown line
  with an empty price is refused; a typed 0 is a price and is kept;
- identity comes from the library at POST — a spec or size that has gone
  since the page loaded refuses the whole form rather than dropping a line;
- the line-item shape is unchanged, so a proforma and a tax invoice raised
  from the new document copy it exactly as before, and every quotation
  written from the catalogue keeps its rows untouched.

The fill rules in the browser are the one piece of this that exists only in
JavaScript, so — `tests/test_picker_js.py`'s arrangement — the page's real
script runs under Node against the real embedded library, through the
rendered controls. Those tests skip when Node is absent.
"""

import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

import pipeline as P
import quotation as Q
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

PIPE = "PIPE-MS-C-1239-SPR"      # 8 sized variants, both rates on every size
AXE = "HYD-FIREMANS-AXE"         # unsized


# ── helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def library(client):
    """The seeded library, through the page that seeds it."""
    r = client.get("/quotation/create")
    assert r.status_code == 200
    return STORE["specs"]


def _spec(code: str) -> tuple:
    return next((sid, s) for sid, s in STORE["specs"].items() if s["code"] == code)


def _both_rated() -> tuple:
    """
    A sized spec whose first variant carries a library SUPPLY rate.

    Kept under its old name — it used to require both rates — because twenty
    tests below call it and every one of them now needs exactly the supply
    rate. The installation rate is irrelevant to a quotation since
    12 September 2026.
    """
    for sid, s in STORE["specs"].items():
        v = s["variants"][0]
        if v.get("label") and v.get("default_supply_base_rate") is not None:
            return sid, s
    raise AssertionError("the seeded library has no sized clause with a supply rate")


def _unrated() -> tuple:
    """A spec whose first variant carries NO supply rate — 22 on the seed."""
    for sid, s in STORE["specs"].items():
        if s["variants"][0].get("default_supply_base_rate") is None:
            return sid, s
    raise AssertionError("the seeded library has no clause without a supply rate")


def _post(client, sel, tax="cgst_sgst", cgst="9", igst="18", **extra):
    data = {"account_name": "Picker Customer", "qtn_date": "2026-09-11",
            "tax_type": tax, "tax_cgst": cgst, "tax_sgst": cgst,
            "tax_igst": igst, "tax_vat": "5",
            "selections_json": json.dumps(sel) if not isinstance(sel, str) else sel}
    data.update(extra)
    return client.post("/quotation/create", data=data)


def _error_of(response) -> str:
    body = response.get_data(as_text=True)
    m = re.search(r'alert-error">&#10007; (.*?)</div>', body, re.S)
    assert m, "the POST did not re-render with an error"
    return m.group(1)


def _newest_quotation() -> dict:
    return list(STORE["quotations"].values())[-1]


def _pick(sid, leg="supply", qty=1, price=None, vidx=0, show=True):
    """
    A pick as the page posts it. `leg` is kept as a parameter so the
    forged-installation tests can post one; the page itself never does.
    """
    return {"sid": sid, "vidx": vidx, "leg": leg, "qty": qty,
            "price": price, "show_price": show}


# ══ 1. The page embeds the library and offers the three controls ═══════════

def test_the_page_embeds_the_library_and_not_the_catalogue(client, library):
    html = client.get("/quotation/create").get_data(as_text=True)
    embedded = json.loads(re.search(
        r'<script type="application/json" id="catalog-data">(.*?)</script>',
        html, re.S).group(1))
    assert set(embedded) == set(library), "the embed is not the whole library"
    one = next(iter(embedded.values()))
    # supply side only — the installation SAC, rate and GST rate are not
    # embedded, because nothing on the page reads them
    assert set(one) == {"code", "title", "category", "supply_hsn",
                        "supply_gst_rate", "variants"}
    assert set(one["variants"][0]) == {"label", "unit", "supply_rate"}
    assert "install" not in html.split('id="catalog-data">')[1].split("</script>")[0]
    assert '"children"' not in html and '"base_price"' not in html, (
        "a catalogue-shaped key reached the page")


def test_the_picker_offers_spec_size_and_qty_and_no_leg(client, library):
    """
    Three controls, not four. The `picker-leg` selector — *Supply +
    Installation* / *Supply only* / *Installation only* — is gone with the
    installation leg (12 September 2026), and its absence is asserted so it
    cannot quietly come back.
    """
    html = client.get("/quotation/create").get_data(as_text=True)
    for control in ("picker-spec", "picker-variant", "picker-qty"):
        assert f'id="{control}"' in html, f"no {control} control"
    assert 'id="picker-leg"' not in html, "Installation is offered again"
    assert 'value="both"' not in html and "Installation only" not in html
    assert 'id="picker-prod"' not in html and "comp-opts-tpl" not in html
    # grouped by category, one option per spec, carrying the spec id —
    # counted INSIDE the spec select, because the address pickers on the same
    # page group by address type and carry optgroups of their own
    select = re.search(r'<select id="picker-spec"[^>]*>(.*?)</select>', html, re.S).group(1)
    assert len(re.findall(r"<optgroup ", select)) == len({s["category"] for s in library.values()})
    ids = re.findall(r'<option value="([^"]+)">', select)
    assert set(ids) == set(library), "every clause is offered, none filtered"


def test_option_text_is_escaped(client, library):
    sid, s = _spec(AXE)
    s["title"] = 'Axe <b>"bold"</b> & co'
    html = client.get("/quotation/create").get_data(as_text=True)
    assert "Axe &lt;b&gt;&quot;bold&quot;&lt;/b&gt; &amp; co" in html
    assert 'Axe <b>"bold"</b>' not in html


# ══ 2. The mapping ═════════════════════════════════════════════════════════

def test_a_pick_becomes_one_supply_line_with_the_right_identity(client, library):
    """
    Retargeted from `test_a_two_leg_pick_becomes_two_lines_with_the_right_
    identity`: one pick, ONE line, the supply side's identity — name, code,
    HSN, unit and rate. The installation row that test also asserted no
    longer exists on a quotation.
    """
    sid, s = _both_rated()
    v = s["variants"][0]
    r = _post(client, [_pick(sid, qty=3, price=v["default_supply_base_rate"])])
    assert r.status_code == 302, _error_of(r)
    q = _newest_quotation()
    assert len(q["line_items"]) == 1, "a pick wrote more than one line"
    sup = q["line_items"][0]

    assert sup["name"] == f"Supply of {s['title']} — {v['label']}"
    assert sup["part_no"] == s["code"]
    assert sup["hsn"] == s["supply_hsn"]
    assert sup["hsn"] != s["install_sac"] or not s["install_sac"]
    assert sup["unit"] == v["unit"]
    assert sup["price"] == v["default_supply_base_rate"]
    assert sup["total"] == sup["price"] * 3
    assert sup["type"] == "item" and sup["depth"] == 0 and sup["qty"] == 3.0
    assert set(sup) == {"type", "name", "part_no", "hsn", "qty", "unit",
                        "price", "total", "depth"}, "the line-item shape moved"

    assert q["subtotal"] == sup["total"]
    assert q["total_qty"] == 3.0
    assert q["grand_total"] == pytest.approx(q["subtotal"] * 1.18)
    assert q["selections"][0]["sid"] == sid


@pytest.mark.parametrize("leg", ["install", "installation", "both", "goods"])
def test_a_forged_installation_leg_is_refused_and_nothing_is_written(client, library, leg):
    """
    The page offers no installation leg; a hand-made POST carrying one is
    refused by line, naming where installation IS billed, and writes nothing.
    A pick with no `leg` at all is supply — that is what the page posts.
    """
    sid, _ = _both_rated()
    before = len(STORE["quotations"])
    r = _post(client, [_pick(sid, price=5), _pick(sid, leg, price=5)])
    assert r.status_code == 200
    err = _error_of(r)
    assert "Line 2" in err and "only the supply of goods" in err
    assert "BOQ" in err and "RA" in err
    assert len(STORE["quotations"]) == before


def test_a_pick_with_no_leg_at_all_is_supply(client, library):
    sid, s = _both_rated()
    pick = _pick(sid, price=5)
    del pick["leg"]
    r = _post(client, [pick])
    assert r.status_code == 302, _error_of(r)
    row = _newest_quotation()["line_items"][0]
    assert row["name"].startswith("Supply of ") and row["hsn"] == s["supply_hsn"]


def test_no_new_quotation_can_carry_an_installation_line(client, library):
    """ABOUT.md §7 gap 37 closes on this: the sell chain writes goods only."""
    sid, s = _both_rated()
    assert _post(client, [_pick(sid, price=5)]).status_code == 302
    for row in _newest_quotation()["line_items"]:
        assert not row["name"].startswith("Installation of")
        assert row["hsn"] == s["supply_hsn"]


def test_an_unsized_clause_carries_no_variant_label(client, library):
    sid, s = _spec(AXE)
    assert len(s["variants"]) == 1 and not s["variants"][0]["label"]
    r = _post(client, [_pick(sid, price=500)])
    assert r.status_code == 302, _error_of(r)
    row = _newest_quotation()["line_items"][0]
    assert row["name"] == f"Supply of {s['title']}"
    assert " — " not in row["name"]


def test_identity_comes_from_the_library_not_the_form(client, library):
    """A crafted POST cannot rename a line, re-code it or change its HSN."""
    sid, s = _both_rated()
    pick = _pick(sid, price=10)
    pick.update({"name": "Forged", "part_no": "FORGED", "hsn": "0000",
                 "unit": "Forged", "label": "Forged"})
    r = _post(client, [pick])
    assert r.status_code == 302, _error_of(r)
    row = _newest_quotation()["line_items"][0]
    assert row["part_no"] == s["code"] and row["hsn"] == s["supply_hsn"]
    assert row["unit"] == s["variants"][0]["unit"]
    assert "Forged" not in row["name"]


def test_the_library_rate_is_a_suggestion_and_a_typed_price_wins(client, library):
    sid, s = _both_rated()
    r = _post(client, [_pick(sid, price=1.25)])
    assert r.status_code == 302, _error_of(r)
    assert _newest_quotation()["line_items"][0]["price"] == 1.25


def test_show_price_off_keeps_the_row_at_no_charge(client, library):
    sid, _ = _both_rated()
    r = _post(client, [_pick(sid, price=999, show=False)])
    assert r.status_code == 302, _error_of(r)
    row = _newest_quotation()["line_items"][0]
    assert (row["price"], row["total"]) == (0.0, 0.0)


# ══ 3. The empty price rule ════════════════════════════════════════════════

@pytest.mark.parametrize("empty", [None, "", "   "])
def test_a_shown_line_with_no_price_is_refused_by_name(client, library, empty):
    # a size the library has no supply rate for — the ordinary source of an
    # empty box, 22 clauses on the seed
    sid, s = _unrated()
    before = len(STORE["quotations"])
    r = _post(client, [_pick(sid, price=empty)])
    assert r.status_code == 200
    err = _error_of(r)
    assert "no price" in err and "Supply of" in err
    assert len(STORE["quotations"]) == before, "a refused POST wrote a quotation"


def test_a_hidden_line_with_no_price_is_accepted_at_no_charge(client, library):
    sid, _ = _both_rated()
    r = _post(client, [_pick(sid, price="", show=False)])
    assert r.status_code == 302, _error_of(r)
    assert _newest_quotation()["line_items"][0]["price"] == 0.0


def test_a_deliberately_typed_zero_is_a_price(client, library):
    sid, _ = _both_rated()
    r = _post(client, [_pick(sid, price=0)])
    assert r.status_code == 302, _error_of(r)
    assert _newest_quotation()["line_items"][0]["price"] == 0.0


# ══ 4. Refusals that name the line ═════════════════════════════════════════

def test_a_spec_that_has_gone_refuses_the_whole_post(client, library):
    sid, _ = _both_rated()
    before = len(STORE["quotations"])
    del STORE["specs"][sid]
    r = _post(client, [_pick(sid, price=5)])
    assert r.status_code == 200
    assert "no longer exists" in _error_of(r)
    assert len(STORE["quotations"]) == before


def test_a_size_that_has_gone_refuses_the_whole_post(client, library):
    sid, s = _both_rated()
    r = _post(client, [_pick(sid, price=5, vidx=len(s["variants"]) + 3)])
    assert r.status_code == 200
    assert "size" in _error_of(r) and "no longer" in _error_of(r)


@pytest.mark.parametrize("bad, fragment", [
    ({"leg": "goods"},       "only the supply of goods"),
    ({"qty": 0},             "greater than zero"),
    ({"qty": "abc"},         "greater than zero"),
    ({"price": -1},          "cannot be negative"),
    ({"price": "abc"},       "not a number"),
])
def test_a_malformed_line_is_refused_with_its_reason(client, library, bad, fragment):
    sid, _ = _both_rated()
    pick = _pick(sid, price=5)
    pick.update(bad)
    r = _post(client, [pick])
    assert r.status_code == 200
    assert fragment in _error_of(r)


@pytest.mark.parametrize("raw", ["not json", "{}", '"str"', "[1, 2]", "[]"])
def test_selection_data_that_is_not_a_list_of_picks_is_refused(client, library, raw):
    r = _post(client, raw)
    assert r.status_code == 200
    err = _error_of(r)
    assert "Invalid item selection" in err or "at least one item" in err


def test_a_refused_post_re_renders_with_the_picks_intact(client, library):
    """The always-return-the-user's-input contract: the picks come back."""
    sid, _ = _unrated()
    sel = [_pick(sid, price="")]
    html = _post(client, sel).get_data(as_text=True)
    prev = re.search(r'id="prev-sel-data">(.*?)</script>', html, re.S).group(1)
    assert json.loads(prev) == sel


# ══ 5. One tax per quotation, never auto-applied ═══════════════════════════

def test_the_tax_section_must_match_the_library_rate(client, library):
    sid, s = _both_rated()
    assert s["supply_gst_rate"] == 18.0
    before = len(STORE["quotations"])
    r = _post(client, [_pick(sid, price=5)], cgst="6")   # 12% on the form
    assert r.status_code == 200
    err = _error_of(r)
    assert "GST rates do not agree" in err
    assert "12%" in err and "CGST 6% + SGST 6%" in err
    assert "Supply of" in err and "18%" in err
    assert len(STORE["quotations"]) == before
    assert "nothing is applied for you" in err


def test_igst_is_compared_to_the_igst_rate(client, library):
    sid, _ = _both_rated()
    assert _post(client, [_pick(sid, price=5)], tax="igst", igst="18").status_code == 302
    r = _post(client, [_pick(sid, price=5)], tax="igst", igst="12")
    assert r.status_code == 200 and "IGST 12%" in _error_of(r)


def test_lines_whose_library_rates_disagree_are_refused_naming_both(client, library):
    """
    Two clauses whose SUPPLY rates disagree — the guard compares
    `supply_gst_rate` only now. It used to be one clause's two legs.
    """
    sid, s = _both_rated()
    other_sid, other = next((k, v) for k, v in STORE["specs"].items()
                            if k != sid and v["variants"][0].get("default_supply_base_rate") is not None)
    other["supply_gst_rate"] = 12.0
    r = _post(client, [_pick(sid, price=5), _pick(other_sid, price=5)])
    assert r.status_code == 200
    err = _error_of(r)
    # the error is escaped at the interpolation site, so compare escaped
    assert P.esc(f"Supply of {s['title']}") in err and "at 18%" in err
    assert P.esc(f"Supply of {other['title']}") in err and "at 12%" in err
    assert "Installation of" not in err


def test_the_installation_gst_rate_is_never_compared(client, library):
    """The other leg's rate may say anything; a quotation does not read it."""
    sid, s = _both_rated()
    s["install_gst_rate"] = 5.0
    r = _post(client, [_pick(sid, price=5)])
    assert r.status_code == 302, _error_of(r)


@pytest.mark.parametrize("tax", ["exempt", "vat"])
def test_exempt_and_vat_are_not_compared(client, library, tax):
    sid, s = _both_rated()
    s["supply_gst_rate"] = 5.0    # would refuse under a GST head
    r = _post(client, [_pick(sid, price=5)], tax=tax)
    assert r.status_code == 302, _error_of(r)


def test_a_clause_with_no_library_rate_makes_no_claim(client, library):
    sid, s = _both_rated()
    s["supply_gst_rate"] = None
    r = _post(client, [_pick(sid, price=5)], cgst="6")
    assert r.status_code == 302, _error_of(r)


def test_nothing_is_ever_applied_for_the_user(client, library):
    """The mismatch refuses; it does not quietly rewrite the Tax section."""
    sid, _ = _both_rated()
    before = len(STORE["quotations"])
    _post(client, [_pick(sid, price=5)], cgst="6")
    assert len(STORE["quotations"]) == before


def test_the_seeded_library_carries_one_rate_on_each_leg():
    """
    Measured 11 September 2026 and pinned: every seeded clause is 18% on both
    legs, so the guard above cannot fire on the seed — it exists for the
    library as it is edited. If this moves, the number in ABOUT.md §5 moves.
    """
    import demo_data
    assert {s["supply_gst_rate"] for s in demo_data.SPECS} == {18.0}
    assert {s["install_gst_rate"] for s in demo_data.SPECS} == {18.0}


def test_the_seeded_library_measured_for_supply_only():
    """
    Measured 12 September 2026 and pinned, for the twenty-eighth block's
    report: of 56 clauses and 86 variants, 5 clauses carry a blank
    `supply_hsn` and 22 have no supply rate on ANY variant (36 of the 86
    variants). Every one of them is still offered; the empty price box is the
    ordinary case for a fifth of the library. If this moves, ABOUT.md §5 moves.
    """
    import demo_data
    specs = demo_data.SPECS
    assert len(specs) == 56 and sum(len(s["variants"]) for s in specs) == 86
    blank_hsn = [s["code"] for s in specs if not (s.get("supply_hsn") or "").strip()]
    no_rate = [s["code"] for s in specs
               if all(v.get("default_supply_base_rate") is None for v in s["variants"])]
    assert len(blank_hsn) == 5, blank_hsn
    assert len(no_rate) == 22, no_rate
    assert sum(1 for s in specs for v in s["variants"]
               if v.get("default_supply_base_rate") is None) == 36


# ══ 6. The create path reads the library and nothing else ══════════════════

def test_the_create_path_reads_the_catalogue_only_behind_the_switch():
    """
    The three unfrozen functions, read at AST level.

    ⚠ **RETARGETED 12 September 2026** (CLIENT_CHANGES.md §0, twenty-eighth
    block): the quotation source FOLLOWS the catalogue switch, so the product
    path is back in these three functions, restored from `1d7725a`, and the
    library path lives in `specpick.py`. The assertion this replaces was, in
    full and verbatim:

        for name, node in funcs.items():
            body = ast.get_source_segment(src, node)
            assert 'STORE["products"]' not in body and "STORE['products']" not in body, name
            assert "ensure_demo_products" not in body, name
        assert "ensure_demo_specs" in ast.get_source_segment(src, funcs["create_quotation"])

    What holds now: every one of the three reads the switch through the one
    accessor, `create_quotation()` seeds the catalogue in one branch and the
    library (through the leaf) in the other, and the library's own code — the
    embed, the POST rebuild, the GST guard — is no longer written here.
    `tests/test_quotation_switch.py` proves the OFF page is `1d7725a`'s bytes.
    """
    src = (REPO / "quotation.py").read_text(encoding="utf8")
    tree = ast.parse(src)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name in ("_product_catalog_json", "_process_selections", "create_quotation")}
    assert len(funcs) == 3
    for name, node in funcs.items():
        body = ast.get_source_segment(src, node)
        assert 'auth.blueprint_hidden("product")' in body, name
        assert "specpick" in body, name
    create = ast.get_source_segment(src, funcs["create_quotation"])
    assert "ensure_demo_products" in create and "SPK.ensure_seeded()" in create
    assert "ensure_demo_specs" not in create, "the library is seeded through the leaf"
    for moved in ("GST rates do not agree", "select a specification", "picker-leg"):
        assert moved not in src, f"{moved!r} is library code and belongs in specpick.py"
    leaf = (REPO / "specpick.py").read_text(encoding="utf8")
    assert "GST rates do not agree" in leaf and "select a specification" in leaf


def test_process_selections_returns_lines_error_and_rates(client, library):
    sid, s = _both_rated()
    lines, err, rates = Q._process_selections([_pick(sid, qty=2, price=7)])
    assert err == "" and len(lines) == 1 and rates == [(lines[0]["name"], 18.0)]
    lines, err, rates = Q._process_selections([_pick("nope", price=7)])
    assert lines == [] and rates == [] and "no longer exists" in err


# ══ 7. Downstream is untouched ═════════════════════════════════════════════

def test_the_document_renders_and_a_proforma_copies_the_rows(client, library):
    sid, s = _both_rated()
    v = s["variants"][0]
    r = _post(client, [_pick(sid, qty=2, price=v["default_supply_base_rate"])])
    assert r.status_code == 302
    q = _newest_quotation()
    view = client.get(f"/quotation/view/{q['id']}").get_data(as_text=True)
    for row in q["line_items"]:
        assert P.esc(row["name"]) in view
        assert P.esc(row["hsn"]) in view
    # the column is headed HSN/SAC on the frozen sheet; a supply line prints
    # an HSN under it, which is the head's own word
    assert "HSN/SAC" in view

    r = client.post(f"/proforma/from/{q['id']}",
                    data={"date": "2026-09-11", "advance_pct": "100",
                          "validity_days": "15"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    pi = list(STORE["proformas"].values())[-1]
    assert pi["line_items"] == q["line_items"]
    assert pi["line_items"] is not q["line_items"], "the PI shares the list rather than copying it"


def test_a_quotation_written_from_the_catalogue_still_renders(client, library):
    q = {
        "id": "q-old-catalogue", "ref": "QT-9902", "date": "2026-08-01",
        "account_name": "Old Customer", "contact_person": "", "to": "Old Customer",
        "tax_type": "cgst_sgst", "cgst_rate": 9.0, "sgst_rate": 9.0, "igst_rate": 18.0,
        "vat_rate": 5.0,
        "tax_info": {"CGST": 45.0, "SGST": 45.0, "total": 90.0, "cgst_rate": 9.0, "sgst_rate": 9.0},
        "subtotal": 500.0, "grand_total": 590.0, "total_qty": 1.0,
        "selections": [{"pid": "a1000001-beef-4000-8000-000000000001", "qty": 1,
                        "price": 500.0, "show_price": True, "components": []}],
        "line_items": [
            {"type": "assembly", "name": "Old Pump Set", "part_no": "OLD-1", "hsn": "8413",
             "qty": 1.0, "unit": "Set", "price": 500.0, "total": 500.0, "depth": 0},
            {"type": "item", "name": "Old Casing", "part_no": "OLD-2", "hsn": "8413",
             "qty": 1.0, "unit": "Nos", "price": 0.0, "total": 0.0, "depth": 1},
        ],
    }
    P.ensure_fields(q)
    STORE["quotations"][q["id"]] = q
    r = client.get(f"/quotation/view/{q['id']}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Old Pump Set" in body and "Old Casing" in body


# ══ 8. The browser side, executed under Node ═══════════════════════════════

_NODE = shutil.which("node")

_STUB = r"""
function el(extra) {
  var e = { value:'', innerHTML:'', textContent:'', disabled:false, checked:false,
            style:{}, options:[], children:[],
            appendChild:function(o){ this.children.push(o); this.options.push(o); },
            addEventListener:function(){}, scrollIntoView:function(){} };
  for (var k in (extra||{})) e[k] = extra[k];
  return e;
}
var BOOT = null;
var STUB = {
  'catalog-data':   el({textContent: LIBRARY_JSON}),
  'prev-sel-data':  el({textContent: PREV_JSON}),
  'add-error':      el(), 'picker-spec': el(), 'picker-variant': el(),
  'picker-qty':     el({value:'1'}),
  'sel-container':  el(), 'empty-notice': el(), 'selections_json': el(), 'qf': el(),
  /* the Tax section's hidden inputs — fillDemoData() writes them unguarded,
     exactly as the real page carries them */
  'hid_cgst': el(), 'hid_sgst': el(), 'hid_igst': el(), 'hid_vat': el()
};
var document = {
  body: {},
  getElementById: function(id){ return STUB[id] || null; },
  createElement:  function(tag){ return el({tagName: tag}); },
  addEventListener: function(evt, fn){ if (evt === 'DOMContentLoaded') BOOT = fn; },
  querySelector: function(){ return null; }
};
var window = { scrollTo: function(){} };
function variantOptions() {
  return STUB['picker-variant'].disabled ? null
       : STUB['picker-variant'].children.map(function(o){ return o.value + '|' + o.textContent; });
}
function pick(sid, vidx, qty) {
  STUB['picker-spec'].value = sid; onSpecPicked();
  if (vidx !== null) STUB['picker-variant'].value = String(vidx);
  STUB['picker-qty'].value = String(qty);
  addProduct();
}
function dump() {
  console.log(JSON.stringify({
    sel: SEL, posted: JSON.parse(STUB['selections_json'].value || '[]'),
    err: STUB['add-error'].textContent, errShown: STUB['add-error'].style.display,
    html: STUB['sel-container'].innerHTML, empty: STUB['empty-notice'].style.display
  }));
}
"""


def _session(client, script: str, prev="[]"):
    """The page's real script, run once, with a sequence of actions after it."""
    html = client.get("/quotation/create").get_data(as_text=True)
    library = re.search(r'<script type="application/json" id="catalog-data">(.*?)</script>',
                        html, re.S).group(1)
    js = html[html.rindex("<script>") + len("<script>"): html.rindex("</script>")]
    harness = (f"var LIBRARY_JSON = {json.dumps(library)};\n"
               f"var PREV_JSON = {json.dumps(prev)};\n" + _STUB)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf8") as fh:
        fh.write(harness + js + "\nBOOT();\n" + script)
        path = fh.name
    try:
        out = subprocess.run(["node", path], capture_output=True, text=True,
                             timeout=30, encoding="utf8")
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_a_sized_spec_offers_its_sizes_and_an_unsized_one_offers_none(client, library):
    pipe, _ = _spec(PIPE)
    axe, _ = _spec(AXE)
    res = _session(client, f"""
        STUB['picker-spec'].value = '{pipe}'; onSpecPicked();
        var sized = variantOptions();
        STUB['picker-spec'].value = '{axe}'; onSpecPicked();
        var unsized = variantOptions();
        console.log(JSON.stringify({{sized: sized, unsized: unsized}}));
    """)
    assert len(res["sized"]) == 8 and res["sized"][0].startswith("0|150mm")
    assert res["unsized"] is None, "an unsized clause must leave the size control disabled"


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_a_pick_adds_one_supply_row_with_the_library_rate(client, library):
    """Retargeted from `test_js_both_legs_add_two_rows_with_library_rates`."""
    sid, s = _both_rated()
    res = _session(client, f"pick('{sid}', 0, 3); dump();")
    assert [r["leg"] for r in res["sel"]] == ["supply"]
    v = s["variants"][0]
    assert res["sel"][0]["price"] == v["default_supply_base_rate"]
    assert res["sel"][0]["qty"] == 3 and res["sel"][0]["sid"] == sid and res["sel"][0]["vidx"] == 0
    assert res["posted"] == res["sel"], "saveJSON() did not serialise the model"
    assert res["html"].count('class="sel-root"') == 1
    assert "Installation" not in res["html"] and "badge-asm" not in res["html"]
    assert "HSN " + s["supply_hsn"] in res["html"]
    assert res["empty"] == "none"


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_the_page_carries_no_leg_control_and_no_leg_code(client, library):
    """
    Retargeted from `test_js_both_skips_a_leg_the_library_does_not_rate` and
    `test_js_both_on_a_wholly_unrated_size_adds_nothing_and_says_so`: there is
    no "both" to skip a leg on and no leg to ask for by name. The script
    carries neither `legLabel` nor an `install_rate` read, and a pick never
    writes anything but `supply`.
    """
    html = client.get("/quotation/create").get_data(as_text=True)
    js = html[html.rindex("<script>"): html.rindex("</script>")]
    assert "legLabel" not in js and "install_rate" not in js and "picker-leg" not in js
    sid, _ = _unrated()
    res = _session(client, f"pick('{sid}', null, 1); dump();")
    assert [r["leg"] for r in res["sel"]] == ["supply"]


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_a_size_with_no_supply_rate_opens_with_an_empty_price(client, library):
    """
    Retargeted from `test_js_an_unrated_leg_asked_for_by_name_opens_with_an_
    empty_price`: the row is still added — every clause is offered — and its
    price box opens EMPTY, never 0, with the placeholder saying why.
    """
    sid, s = _unrated()
    res = _session(client, f"pick('{sid}', null, 1); dump();")
    assert res["sel"][0]["leg"] == "supply" and res["sel"][0]["price"] == ""
    assert res["errShown"] != "block", "an unrated size must still be added"
    assert 'value=""' in res["html"] and 'placeholder="no library rate"' in res["html"]
    assert 'value="0"' not in res["html"].split('data-field="price"')[1][:40]


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_an_emptied_price_stays_empty_and_a_typed_zero_stays_zero(client, library):
    sid, _ = _both_rated()
    res = _session(client, f"""
        pick('{sid}', 0, 1);
        pick('{sid}', 1, 1);
        onRootChange(0, 'price', '');
        onRootChange(1, 'price', '0');
        dump();
    """)
    assert res["sel"][0]["price"] == "" and res["sel"][1]["price"] == 0
    assert res["posted"][0]["price"] == "" and res["posted"][1]["price"] == 0


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_removing_a_row_re_renders_the_rest(client, library):
    sid, _ = _both_rated()
    res = _session(client, f"pick('{sid}', 0, 1); pick('{sid}', 1, 1); removeRoot(0); dump();")
    assert [r["vidx"] for r in res["sel"]] == [1]
    assert res["html"].count('class="sel-root"') == 1


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_demo_data_picks_a_clause_with_a_supply_rate(client, library):
    """Retargeted: one priced supply row, from a clause with a supply rate."""
    res = _session(client, "fillDemoData(); dump();")
    assert [r["leg"] for r in res["sel"]] == ["supply"]
    assert res["sel"][0]["price"] not in ("", None) and res["sel"][0]["qty"] == 2
    spec = STORE["specs"][res["sel"][0]["sid"]]
    assert spec["variants"][0]["default_supply_base_rate"] is not None


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_a_rejected_post_restores_the_picks(client, library):
    sid, _ = _both_rated()
    prev = json.dumps([_pick(sid, qty=4, price="")])
    res = _session(client, "dump();", prev=prev)
    assert len(res["sel"]) == 1 and res["sel"][0]["qty"] == 4
    assert res["html"].count('class="sel-root"') == 1


@pytest.mark.skipif(_NODE is None, reason="node not installed")
def test_js_the_row_escapes_the_title(client, library):
    sid, s = _both_rated()
    s["title"] = 'Pipe <img src=x onerror=alert(1)> & "co"'
    res = _session(client, f"pick('{sid}', 0, 1); dump();")
    assert "<img" not in res["html"]
    assert "&lt;img src=x onerror=alert(1)&gt; &amp; &quot;co&quot;" in res["html"]
