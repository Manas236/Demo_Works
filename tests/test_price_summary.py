"""
The PRICE SUMMARY cover and the print orientation (25 November 2026,
CLIENT_CHANGES.md §0 ninetieth block).

What is held here, by ruling:

* R8: the cover's figures are the detail pages' figures to the paisa, on a
  split BOQ, an SITC BOQ, a BOQ with an EMPTY section (printed 0.00, not
  hidden), a BOQ with the round off on, and a quotation with and without tax.
* R3: the terms are a SNAPSHOT. A document prints its own copy, never the live
  /settings list; the seed never overwrites an edited list; the backfill is
  idempotent and touches only documents lacking terms.
* R2: the tick, default ON for a document that predates it.
* R5/R6: the orientation is stored and the whole print follows it; portrait
  re-lays the BOQ out and still carries every figure landscape carries.
* R10: every new user string is escaped; no em dash in new text.
"""

import copy
import json
import re

import pytest

from store import STORE

import pricesummary as PS


# ── helpers ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _keep_the_settings():
    """`STORE["settings"]` is not reset between tests, and tests here rewrite
    the summary record and post /settings. Put the whole collection back as
    found, so no later file (the /settings page golden above all) sees it."""
    import copy as _c
    import branding as B
    import settings as S
    saved = _c.deepcopy(STORE["settings"])
    yield
    STORE["settings"].clear()
    STORE["settings"].update(saved)
    B.apply_settings(S.load_saved())


def _cover(html: str) -> str:
    m = re.search(r'<div class="ps-cover">(.*?)</table>', html, re.S)
    assert m, "the price summary cover is not on the page"
    return m.group(1)


def _cover_rows(html: str) -> dict:
    """{sr or label: [amount strings]} from the cover table."""
    out = {}
    for tr in re.findall(r"<tr(?: class=\"ps-tot\")?>(.*?)</tr>", _cover(html), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if not cells:
            continue
        amts = re.findall(r'<td class="ps-amt">(.*?)</td>', tr, re.S)
        out[cells[0].strip()] = [a.strip() for a in amts]
    return out


def _detail_subtotals(html: str) -> dict:
    """{section code: [amount strings]} from the detail sheet's subtotal rows."""
    out = {}
    for code, tail in re.findall(
            r'BASIC VALUE SUBTOTAL \(([^)]*)\) &gt;&gt;&gt;&gt;</td>(.*?)</tr>', html, re.S):
        out[code] = re.findall(r'<td class="b-amt">(.*?)</td>', tail)
    return out


def _grand_amounts(html: str) -> list:
    g = html[html.index('<div class="boq-grand">'):]
    g = g[:g.index("</table>")]
    return re.findall(r'<td class="bg-amt">([^<]*)</td>', g)


@pytest.fixture()
def demo(client):
    import boq as BQ
    BQ.ensure_demo_boq()
    bid = next(iter(STORE["boqs"]))
    return bid, STORE["boqs"][bid]


def _sitc_copy(src: dict, new_id: str, empty_section: str = "C") -> dict:
    """An SITC schedule from the demo, with one section priced at nil."""
    s = copy.deepcopy(src)
    s["id"], s["ref"], s["rate_basis"] = new_id, "SF/BOQ/26-27/0098", "sitc"
    for li in s["line_items"]:
        if li.get("is_header"):
            continue
        sr, ir = li.get("supply_rate"), li.get("install_rate")
        li["supply_rate"] = (float(sr or 0) + float(ir or 0)
                             if (sr is not None or ir is not None) else None)
        li["install_rate"] = li["install_amount"] = None
        q = li.get("total_qty")
        if li.get("section") == empty_section and li["supply_rate"] is not None:
            li["supply_rate"] = 0.0
        li["supply_amount"] = (None if q is None or li["supply_rate"] is None
                               else round(float(q) * li["supply_rate"], 2))
    STORE["boqs"][new_id] = s
    return s


# ── R8: the cover matches the detail to the paisa ──────────────────────────

def test_split_boq_cover_equals_the_detail_subtotals_and_totals(client, demo):
    bid, b = demo
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    cover, detail = _cover_rows(html), _detail_subtotals(html)
    codes = [s["code"] for s in b["sections"]]
    assert codes and set(codes) == set(detail)
    for c in codes:
        assert cover[c] == detail[c], c
    grand = _grand_amounts(html)
    # TOTAL (A+B+C): supply, installation; TOTAL BASIC VALUE: the sum.
    assert cover["Total"] == grand[:2]
    assert cover["Total Basic Value"] == ["", grand[3]]
    assert '<div class="ps-band">TAXES WILL BE EXTRA</div>' in html


def test_sitc_boq_cover_has_one_column_and_an_empty_section_prints_zero(client, demo):
    _bid, b = demo
    s = _sitc_copy(b, "sitc-1", empty_section="C")
    import boq as BQ
    assert BQ.section_totals(s, "C") == (0.0, 0.0)
    html = client.get("/boq/print/sitc-1").get_data(as_text=True)
    cov = _cover(html)
    assert "Supply + Installation (SITC)" in cov
    assert "Installation Amount" not in cov and "Supply Amount" not in cov
    cover, detail = _cover_rows(html), _detail_subtotals(html)
    assert cover["C"] == ["0.00"] == detail["C"], "the empty section must print 0.00"
    for c in ("A", "B", "C"):
        assert cover[c] == detail[c]
    assert cover["Total"] == [_grand_amounts(html)[0]]


def test_round_off_on_the_cover_matches_the_sheet(client, demo):
    import boq as BQ
    import roundoff as RO
    bid, b = demo
    b[RO.FIELD] = True
    _t, ro, rounded = BQ.grand_of(b)
    assert abs(ro) >= 0.005, "the demo total must not already be whole for this test"
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    cover = _cover_rows(html)
    assert cover["Round Off"][-1] == RO.label(ro)
    assert cover["Grand Total"][-1] == BQ._inr(rounded)
    assert BQ._inr(rounded) in _grand_amounts(html)


def _quote(**over):
    q = {"id": "q-ps", "ref": "QT-0042", "date": "2026-11-25",
         "account_name": "Reliance Industries Ltd",
         "to": "Reliance Industries Ltd\nJamnagar",
         "ship_same": "on", "line_items": [
             {"type": "item", "depth": 0, "part_no": "P1", "name": "Pump",
              "hsn": "", "qty": 2.0, "unit": "Nos", "price": 1000.25, "total": 2000.50}],
         "subtotal": 2000.50, "tax_type": "cgst_sgst",
         "tax_info": {"CGST": 180.05, "SGST": 180.05, "cgst_rate": 9.0,
                      "sgst_rate": 9.0, "total": 360.10},
         "grand_total": 2361.0, "round_off": 0.40, "round_off_on": True,
         "total_qty": 2.0}
    q.update(over)
    import pipeline as P
    P.ensure_fields(q)
    STORE["quotations"][q["id"]] = q
    return q


def test_quotation_cover_shows_the_documents_own_tax_and_grand_total(client):
    _quote()
    html = client.get("/quotation/view/q-ps").get_data(as_text=True)
    cover = _cover_rows(html)
    assert cover["A"] == ["2,000.50"]
    assert cover["CGST @ 9%"] == ["180.05"] and cover["SGST @ 9%"] == ["180.05"]
    assert cover["Round off"] == ["0.40"] or cover["Round off"] == ["+0.40"]
    assert cover["Grand Total"] == ["2,361.00"]
    # The same figures print in the detail rows below.
    assert html.count("2,361.00") >= 2 and html.count("180.05") >= 4
    assert 'class="ps-band"' not in html, "a document that prints GST must not say taxes extra"
    assert "<th>Amount</th>" in _cover(html)


def test_quotation_without_tax_carries_the_tax_line(client):
    _quote(tax_type="exempt", tax_info={"total": 0.0}, grand_total=2000.50,
           round_off=0.0)
    html = client.get("/quotation/view/q-ps").get_data(as_text=True)
    cover = _cover_rows(html)
    assert cover["Total"] == ["2,000.50"]
    assert '<div class="ps-band">TAXES WILL BE EXTRA</div>' in html


def test_quotation_subject_and_row_default_and_override(client):
    _quote(lead_subtype="SPRINKLER SYSTEM")
    html = client.get("/quotation/view/q-ps").get_data(as_text=True)
    assert "Reliance Industries Ltd Quotation" in _cover(html)
    assert "SPRINKLER SYSTEM" in _cover(html)
    STORE["quotations"]["q-ps"].update(summary_subject="Reliance Jamnagar Site Quotation",
                                       summary_system="Fire Protection, Phase 2")
    cov = _cover(client.get("/quotation/view/q-ps").get_data(as_text=True))
    assert "Reliance Jamnagar Site Quotation" in cov and "Fire Protection, Phase 2" in cov


# ── R2: the tick ───────────────────────────────────────────────────────────

def test_an_existing_document_gets_the_cover_and_the_tick_turns_it_off(client, demo):
    bid, b = demo
    assert PS.FIELD_ON not in b
    assert 'class="ps-cover"' in client.get(f"/boq/print/{bid}").get_data(as_text=True)
    b[PS.FIELD_ON] = False
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert "ps-cover" not in html and "PRICE SUMMARY" not in html
    _quote(price_summary_on=False)
    assert "ps-cover" not in client.get("/quotation/view/q-ps").get_data(as_text=True)


def test_the_cover_does_not_reach_the_internal_view(client, demo):
    bid, _b = demo
    assert "ps-cover" not in client.get(f"/boq/view/{bid}").get_data(as_text=True)


# ── R3: the terms are a snapshot ───────────────────────────────────────────

def test_seed_is_the_clients_eleven_verbatim_and_never_overwrites(client):
    """Superseded on 26 Nov 2026 by the LIBRARY (§0 ninety-first block): the
    eleven are still the seed, now the first eleven library terms, ON."""
    STORE["settings"].pop(PS.RECORD, None)
    PS.ensure_seeded()
    rec = STORE["settings"][PS.RECORD]
    on = [e["text"] for e in rec["library"] if e["on"]]
    assert on == list(PS.DEFAULT_TERMS)
    assert on[9] == "10% retention payment completion of work."
    assert rec["title"] == "PRICE SUMMARY FOR FIRE PROTECTION SYSTEM"
    assert rec["tax_line"] == "TAXES WILL BE EXTRA"
    rec["library"] = [{"id": "x", "text": "Only this one.", "category": "Legal", "on": True}]
    PS.ensure_seeded()
    assert [e["text"] for e in STORE["settings"][PS.RECORD]["library"]] == ["Only this one."]


def test_create_copies_the_default_and_print_never_reads_the_live_list(client):
    import test_boq as TB
    PS.save_settings("", "", ["Default one.", "Default two."])
    r = client.post("/boq/create", data=TB.FORM)       # no editor on this POST
    assert r.status_code == 302
    bid = next(iter(STORE["boqs"]))
    assert STORE["boqs"][bid][PS.FIELD_TERMS] == ["Default one.", "Default two."]
    PS.save_settings("", "", ["Changed later."])
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert "Default two." in html and "Changed later." not in html


def test_the_documents_own_edited_terms_print_in_order(client):
    import test_boq as TB
    form = dict(TB.FORM)
    form.update({PS.MARK_TERMS: "1", PS.MARK_ON: "1", PS.FIELD_ON: "1"})
    data = list(form.items()) + [(PS.FIELD_TERM, "Second."), (PS.FIELD_TERM, "  "),
                                 (PS.FIELD_TERM, "First?")]
    from werkzeug.datastructures import MultiDict
    r = client.post("/boq/create", data=MultiDict(data))
    assert r.status_code == 302
    bid = next(iter(STORE["boqs"]))
    assert STORE["boqs"][bid][PS.FIELD_TERMS] == ["Second.", "First?"]
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert html.index("Second.") < html.index("First?")


def test_an_unticked_form_stores_off(client):
    import test_boq as TB
    form = dict(TB.FORM)
    form.update({PS.MARK_ON: "1"})                    # the tick offered, not ticked
    assert client.post("/boq/create", data=form).status_code == 302
    b = next(iter(STORE["boqs"].values()))
    assert b[PS.FIELD_ON] is False


def test_settings_page_saves_reorders_and_removes(client):
    from werkzeug.datastructures import MultiDict
    import settings as S
    page = client.get("/settings/").get_data(as_text=True)
    assert "Terms library" in page
    # Post the page's other sections as they stand, with the summary edited.
    data = MultiDict([(k, v) for k, v in S.load_saved().items()])
    data.add("charge_heads", "\n".join(S.charge_heads()))
    data.add("measurement_columns", S.measurement_columns_text())
    data.add(PS.MARK_LIB, "1")
    data.add("ps_title", "SUMMARY")
    data.add("ps_tax_line", "")
    for i, t, c, on in (("", "Term B", "Legal", "1"), ("", "Term A", "Site", "1"),
                        ("", "Term C", "Nonsense", "0"), ("", "   ", "Site", "1")):
        data.add(PS.LIB_ID, i)
        data.add(PS.LIB_TEXT, t)
        data.add(PS.LIB_CAT, c)
        data.add(PS.LIB_ON, on)
    r = client.post("/settings/", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:3000]
    cfg = PS.settings_of()
    assert cfg["terms"] == ["Term B", "Term A"]
    assert [(e["text"], e["category"], e["on"]) for e in cfg["library"]] == [
        ("Term B", "Legal", True), ("Term A", "Site", True),
        ("Term C", "Commercial", False)], "an unknown category falls back; a blank row goes"
    assert cfg["title"] == "SUMMARY"
    assert cfg["tax_line"] == "TAXES WILL BE EXTRA", "blank reads as the default"


# ── the backfill ───────────────────────────────────────────────────────────

def test_backfill_is_dry_by_default_idempotent_and_never_overwrites():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "backfill_terms",
        pathlib.Path(__file__).resolve().parent.parent / "tools" / "backfill_terms.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    store = {"boqs": {"a": {}, "b": {PS.FIELD_TERMS: []}, "c": {PS.FIELD_TERMS: ["x"]}},
             "quotations": {"q": {}}}
    PS.save_settings("", "", ["T1", "T2"])
    dry = mod.backfill(store, write=False)
    assert dry["boqs"] == {"total": 3, "lacking": 1, "written": 0}
    assert dry["quotations"]["lacking"] == 1
    assert PS.FIELD_TERMS not in store["boqs"]["a"], "a dry run wrote"
    res = mod.backfill(store, write=True)
    assert res["boqs"]["written"] == 1 and res["quotations"]["written"] == 1
    assert store["boqs"]["a"][PS.FIELD_TERMS] == ["T1", "T2"]
    assert store["boqs"]["b"][PS.FIELD_TERMS] == [], "an emptied list is a choice"
    assert store["boqs"]["c"][PS.FIELD_TERMS] == ["x"]
    again = mod.backfill(store, write=True)
    assert again["boqs"]["written"] == 0 and again["quotations"]["written"] == 0


# ── R5 / R6: the orientation ───────────────────────────────────────────────

def test_boq_defaults_to_landscape_and_the_switch_stores_the_choice(client, demo):
    bid, b = demo
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert 'class="boq-table boq-portrait"' not in html
    assert "@page { size:A4 portrait; }" not in html
    assert 'aria-pressed="true">Landscape' in html
    r = client.post(f"/boq/print/{bid}/orientation", data={PS.FIELD_ORIENT: "portrait"})
    assert r.status_code == 302 and b[PS.FIELD_ORIENT] == "portrait"
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert 'class="boq-table boq-portrait"' in html
    assert "@page { size:A4 portrait; }" in html
    client.post(f"/boq/print/{bid}/orientation", data={PS.FIELD_ORIENT: "sideways"})
    assert b[PS.FIELD_ORIENT] == "portrait", "a bad value is refused, nothing written"


def test_quotation_defaults_to_portrait_and_landscape_is_the_whole_sheet(client):
    _quote()
    html = client.get("/quotation/view/q-ps").get_data(as_text=True)
    assert "sheet-landscape" not in html
    client.post("/quotation/print/q-ps/orientation", data={PS.FIELD_ORIENT: "landscape"})
    html = client.get("/quotation/view/q-ps").get_data(as_text=True)
    assert '<div class="doc-outer sheet-landscape">' in html
    assert "size:A4 landscape" in html


def _row_figures(row_html: str) -> set:
    return set(re.findall(r"\d[\d,]*\.\d\d|(?<=\s)\d+(?=\s|<)", re.sub(r"<[^>]+>", " ", row_html)))


def test_portrait_carries_every_figure_landscape_carries(client, demo):
    """Area quantities, rates, discounts' net rates and amounts: nothing that
    prints in landscape is missing from portrait, line by line."""
    import boq as BQ
    bid, b = demo
    # A discount on a line, so the Disc % and Net Rate columns exist.
    li = next(x for x in b["line_items"] if not x.get("is_header")
              and x.get("supply_rate") and x.get("area_qty"))
    li["supply_disc_pct"] = 10.0
    li["supply_amount"] = BQ.amount_of(li.get("total_qty"), BQ.net_rate(li, "supply"))

    def rows(html):
        body = html[html.index('<div class="doc-box">'):]
        return re.findall(r'<tr class="row-line">(.*?)</tr>', body, re.S)

    land = rows(client.get(f"/boq/print/{bid}").get_data(as_text=True))
    b[PS.FIELD_ORIENT] = "portrait"
    port_html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    port = rows(port_html)
    assert len(land) == len(port) > 0
    for lrow, prow in zip(land, port):
        lf = set(re.findall(r'<td class="b-(?:area|qty|rate|amt)">([^<]+)</td>', lrow))
        missing = {f for f in lf if f not in prow}
        assert not missing, f"portrait dropped {missing}"
    assert "Net " in port_html and 'class="b-sub"' in port_html


def test_the_make_column_prints_in_both_orientations_only_when_a_line_has_one(client, demo):
    bid, b = demo
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert 'class="b-make"' not in html, "no make on any line: no column"
    li = next(x for x in b["line_items"] if not x.get("is_header"))
    li["remark"] = "internal note; Make: Kirloskar"
    for o in ("landscape", "portrait"):
        b[PS.FIELD_ORIENT] = o
        html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
        assert '<th class="b-make"' in html and ">Kirloskar</td>" in html, o
        assert "internal note" not in html, "only the make leaves the remark"


def test_the_print_grids_still_add_up_with_the_make_column(client, demo):
    bid, b = demo
    next(x for x in b["line_items"] if not x.get("is_header"))["remark"] = "Make: X"
    for o in ("landscape", "portrait"):
        b[PS.FIELD_ORIENT] = o
        html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
        for tbl in re.findall(r'<table class="boq-table[^"]*">(.*?)</table>', html, re.S):
            width = tbl[:tbl.index("</colgroup>")].count("<col ")
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
                if "rowspan" in tr:
                    continue
                cells = re.findall(r"<t[dh]([^>]*)>", tr)
                n = sum(int((re.search(r'colspan="(\d+)"', c) or [0, 1])[1]) for c in cells)
                if 'class="b-area"' in tr and "<th" in tr:
                    continue          # the area-name row under a rowspanned head
                assert n == width, (o, n, width, tr[:200])


# ── R10: escaping, and no em dash in new text ──────────────────────────────

def test_every_new_string_is_escaped(client, demo):
    bid, b = demo
    evil = '<script>alert(1)</script>'
    b[PS.FIELD_TERMS] = [evil]
    b["project_name"] = evil
    PS.save_settings(evil, evil, [evil])
    html = client.get(f"/boq/print/{bid}").get_data(as_text=True)
    assert evil not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    q = _quote(summary_subject=evil, summary_system=evil,
               tax_type="exempt", tax_info={"total": 0.0})
    q[PS.FIELD_TERMS] = [evil]
    assert evil not in client.get("/quotation/view/q-ps").get_data(as_text=True)
    assert evil not in client.get("/settings/").get_data(as_text=True)
    assert evil not in client.get(f"/boq/edit/{bid}").get_data(as_text=True)
    assert evil not in client.get("/quotation/edit/q-ps").get_data(as_text=True)


def test_no_em_dash_in_the_new_text():
    import inspect
    src = inspect.getsource(PS)
    code = re.sub(r'"""(.*?)"""', "", src, flags=re.S)
    code = "\n".join(line.split("#", 1)[0] for line in code.splitlines())
    assert "—" not in code and "&mdash;" not in code
    for t in PS.DEFAULT_TERMS:
        assert "—" not in t


# ── the quotation's own form ───────────────────────────────────────────────

def test_quotation_edit_saves_the_tick_the_text_and_the_terms(client):
    import test_quotation_edit as TQ
    from werkzeug.datastructures import MultiDict
    q = TQ._q()
    STORE["quotations"][q["id"]] = q
    page = client.get(f"/quotation/edit/{q['id']}").get_data(as_text=True)
    assert "Include price summary page" in page and PS.MARK_TERMS in page
    # A quotation with no terms stored opens with a COPY of the default.
    assert PS.settings_of()["terms"][0][:30] in page
    data = MultiDict(list(TQ._form(q).items()))
    data.add(PS.MARK_ON, "1")                     # offered, left unticked
    data.add(PS.MARK_TERMS, "1")
    data.add(PS.FIELD_TERM, "Only term.")
    data.add(PS.FIELD_SUBJECT, "Jamnagar Site Quotation")
    data.add(PS.FIELD_SYSTEM, "")
    r = client.post(f"/quotation/edit/{q['id']}", data=data)
    assert r.status_code == 302
    q = STORE["quotations"][q["id"]]
    assert q[PS.FIELD_ON] is False
    assert q[PS.FIELD_TERMS] == ["Only term."]
    assert q[PS.FIELD_SUBJECT] == "Jamnagar Site Quotation"
    assert q[PS.FIELD_SYSTEM] == ""


def test_quotation_create_form_offers_the_section_in_library_mode(client):
    page = client.get("/quotation/create").get_data(as_text=True)
    assert "Include price summary page" in page
    assert page.index("Price Summary Page") < page.index("SECTION 4: TAX / DUTY")
