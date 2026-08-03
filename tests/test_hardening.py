"""
The hardening pass — one test per bug found, named for the class it belongs to.

Every test here failed before the fix it guards. They are grouped by class
rather than by module, because each of these was found by asking "where else
does this shape appear?" rather than by looking at the reported case.
"""

import json
import re

import pytest

import boq
import spec
from store import STORE


@pytest.fixture()
def seeded(client):
    client.get("/boq/")
    return client


# ═══ CLASS: state that lives only in the developer's database ═══════════════

def test_company_identity_is_seeded_not_hand_entered(client):
    """
    BUG 1. The specimen identity was typed into one working database and never
    seeded, so dropping that database took the letterhead, GSTIN, PAN and the
    whole bank block with it and every document started printing amber chips.
    """
    import branding as B
    import settings

    STORE["settings"].clear()
    STORE["_settings_seeded"] = False
    settings.ensure_demo_settings()
    B.apply_settings(settings.load_saved())

    assert len(STORE["settings"]) == 1
    filled = [v for v in B.current_settings().values() if str(v or "").strip()]
    assert len(filled) == 15, f"only {len(filled)} of 15 company fields filled"
    assert B.COMPANY_GSTIN == "27AAAAA0000A1Z5"
    assert B.BANK_NAME == "SPECIMEN BANK LTD."


def test_the_seeder_never_overwrites_a_real_identity(client):
    import settings

    STORE["settings"].clear()
    STORE["settings"][settings.RECORD_ID] = {"COMPANY_GSTIN": "27ABCDE1234F1Z5"}
    STORE["_settings_seeded"] = False
    settings.ensure_demo_settings()
    assert STORE["settings"][settings.RECORD_ID] == {"COMPANY_GSTIN": "27ABCDE1234F1Z5"}


def test_every_reference_collection_has_a_seeder(client):
    """
    The class, generalised. Reference and configuration data must survive a
    fresh install; transactional records must NOT be invented.
    """
    import db

    client.get("/")
    for u in ("/product/", "/address/", "/spec/", "/boq/", "/settings/"):
        client.get(u)

    seeded = {"products", "addresses", "specs", "boqs", "settings"}
    transactional = {"quotations", "proformas", "invoices", "purchases"}
    assert seeded | transactional == set(db.COLLECTIONS)

    for coll in seeded:
        assert STORE[coll], f"{coll} is empty on a fresh install — no seeder"
    for coll in transactional:
        assert not STORE[coll], f"{coll} was seeded — real documents must not be invented"


def test_seed_flags_are_not_persisted(client):
    """Dropping the database has to refill the reference data, which is only
    true while the flags stay out of COLLECTIONS."""
    import db

    for flag in ("_seeded", "_addr_seeded", "_spec_seeded",
                 "_boq_seeded", "_settings_seeded"):
        assert flag in STORE
        assert flag not in db.COLLECTIONS


# ═══ CLASS: a JS-added row that diverges from the server-rendered one ═══════

def test_added_variant_row_is_cloned_from_a_server_template(seeded, client):
    """
    BUG 2. `_variant_row()` already emits `<div class="var-row">`, and the JS
    wrapped it in a SECOND one — a grid nested inside its own grid cell, so the
    inputs collapsed to one column's width.
    """
    sp = spec.spec_by_code("HYD-FIREMANS-AXE")
    html = client.get(f"/spec/edit/{sp['id']}").get_data(as_text=True)

    assert '<template id="var-tpl">' in html
    assert "cloneNode(true)" in html
    # The old shape: building a wrapper and assigning innerHTML into it.
    assert "createElement('div')" not in html
    assert "row.innerHTML" not in html

    tpl = re.search(r'<template id="var-tpl">(.*?)</template>', html, re.S).group(1)
    assert tpl.count('class="var-row"') == 1, "template must not nest .var-row"
    assert tpl.strip().startswith('<div class="var-row">')


def test_the_template_row_matches_a_rendered_row_field_for_field(seeded, client):
    sp = spec.spec_by_code("HYD-FIREMANS-AXE")
    html = client.get(f"/spec/edit/{sp['id']}").get_data(as_text=True)
    tpl = re.search(r'<template id="var-tpl">(.*?)</template>', html, re.S).group(1)
    rows = html.split('id="var-rows"')[1].split("</div>\n\n      <button")[0]
    for field in ("var_label", "var_dimension", "var_dim_unit",
                  "var_unit", "var_supply", "var_install"):
        assert f'name="{field}"' in tpl, field
        assert f'name="{field}"' in rows, field


def test_template_contents_are_not_submitted(seeded, client):
    """
    A <template> is inert — its inputs are not part of the form. If that ever
    stopped being true, every save would gain a phantom blank variant.
    """
    r = client.post("/spec/add", data={
        "code": "TPL-1", "title": "t", "category": "Other", "spec_text": "x",
        "supply_hsn": "", "install_sac": "", "supply_gst_rate": "18",
        "install_gst_rate": "18",
        "var_label": ["100mm", "150mm"], "var_dimension": ["100", "150"],
        "var_dim_unit": ["mm", "mm"], "var_unit": ["Mtrs", "Mtrs"],
        "var_supply": ["1", "2"], "var_install": ["3", "4"]})
    assert r.status_code == 302
    assert len(spec.spec_by_code("TPL-1")["variants"]) == 2


# ═══ CLASS: server-side template injection via render_template_string ══════

@pytest.mark.parametrize("payload,evaluated", [
    ("{{ 7*7 }}", "MARK49MARK"),
    ("{{ config }}", "qms-demo-secret-2024"),
    ("{{ ''.__class__.__mro__ }}", "MARK<class"),
    ("{{ self.__init__.__globals__ }}", "MARK{'"),
])
def test_jinja_in_user_text_is_never_evaluated(seeded, client, payload, evaluated):
    """
    `pipeline.esc()` escapes < > & " ' and deliberately not braces, so any page
    re-parsed by Jinja executes template syntax that came from a user. These
    views return finished HTML instead.
    """
    client.post("/spec/add", data={
        "code": "SSTI", "title": "t", "category": "Other",
        "spec_text": f"MARK{payload}MARK",
        "supply_hsn": "", "install_sac": "", "supply_gst_rate": "18",
        "install_gst_rate": "18", "var_label": [""], "var_dimension": [""],
        "var_dim_unit": [""], "var_unit": ["Nos"], "var_supply": [""],
        "var_install": [""]})
    sp = spec.spec_by_code("SSTI")
    html = client.get(f"/spec/view/{sp['id']}").get_data(as_text=True)
    assert evaluated not in html, f"{payload} was evaluated by Jinja"
    # It should survive as the literal text it is. The braces reach the page
    # untouched — they are not HTML-significant — so the marker plus the
    # opening delimiter is enough to prove nothing consumed it.
    assert "MARK{{" in html or "MARK{%" in html


def test_a_malformed_template_tag_cannot_break_the_boq_form(seeded, client):
    """
    The denial-of-service half. /boq/create embeds all 56 clauses, so one
    unclosed {% %} used to 500 the whole form for everybody.
    """
    assert client.get("/boq/create").status_code == 200
    client.post("/spec/add", data={
        "code": "BAD", "title": "t", "category": "Other",
        "spec_text": "{% for x in y %}", "supply_hsn": "", "install_sac": "",
        "supply_gst_rate": "18", "install_gst_rate": "18", "var_label": [""],
        "var_dimension": [""], "var_dim_unit": [""], "var_unit": ["Nos"],
        "var_supply": [""], "var_install": [""]})
    assert client.get("/boq/create").status_code == 200
    assert client.get("/spec/").status_code == 200
    sp = spec.spec_by_code("BAD")
    assert client.get(f"/spec/view/{sp['id']}").status_code == 200
    assert client.get(f"/spec/edit/{sp['id']}").status_code == 200


# ═══ CLASS: user text embedded in a <script> block ═════════════════════════

def test_script_close_in_a_clause_cannot_break_out(seeded, client):
    """
    json.dumps does not escape `<`, so a clause containing `</script>` closed
    the block and everything after it parsed as HTML.
    """
    sp = spec.spec_by_code("HYD-FIREMANS-AXE")
    sp["spec_text"] = '</script><script>alert(1)</script>'
    html = client.get("/boq/create").get_data(as_text=True)
    assert "</script><script>alert(1)" not in html
    assert html.count("<script>") == html.count("</script>") == 1


def test_script_safe_json_round_trips(seeded):
    original = {"a": '</script> & <b> "q" \'s\''}
    encoded = boq._json_for_script(original)
    assert "<" not in encoded and ">" not in encoded and "&" not in encoded
    assert json.loads(encoded) == original


def test_all_three_embedded_payloads_are_script_safe(seeded, client):
    """The picker, the address book and the editor model are all embedded."""
    src = open(boq.__file__, encoding="utf8").read()
    # Two are encoded at the call site; the picker payload is encoded inside
    # the function that builds it.
    for token in ("BOQ_ADDR", "BOQ_BOOT"):
        assert f'.replace("{token}", _json_for_script(' in src, token
    assert '.replace("BOQ_SPECS", _spec_catalog_json())' in src
    body = src.split("def _spec_catalog_json")[1].split("\ndef ")[0]
    assert "_json_for_script(" in body, "the picker payload is not script-safe"
    assert "json.dumps(" not in body, "raw json.dumps in the picker payload"


# ═══ CLASS: unescaped user text on the printed document ════════════════════

def test_header_meta_on_the_document_is_escaped(seeded, client):
    """
    `quotation._meta()` does not escape — importing a helper does not import
    its discipline. Five header fields went to paper raw.
    """
    payload = {"sections": [{"code": "A", "title": "T", "areas": []}],
               "lines": [{"item_no": "1", "parent_item_no": "", "section": "A",
                          "is_header": False, "description": "d", "remark": "",
                          "unit": "Nos", "area_qty": {}, "total_qty": "1",
                          "supply_base_rate": "", "supply_escalation_pct": "",
                          "supply_rate": "10", "supply_hsn": "",
                          "supply_gst_rate": "18", "install_base_rate": "",
                          "install_escalation_pct": "", "install_rate": "",
                          "install_sac": "", "install_gst_rate": "18"}]}
    xss = '<script>alert("x")</script>'
    client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": xss, "site_location": xss,
        "account_name": xss, "rate_basis_label": xss, "payment_terms": xss,
        "delivery_terms": xss, "notes": xss, "boq_json": json.dumps(payload)})
    bid = [k for k, v in STORE["boqs"].items() if v.get("project_name") == xss][0]
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert xss not in html
    assert "&lt;script&gt;alert" in html


# ═══ CLASS: a dropdown that silently rewrites an unrecognised value ════════

def test_demo_payment_terms_are_not_rewritten_by_the_dropdown(seeded, client):
    """
    The Sify schedule's payment terms are the client's own wording and are not
    in `quotation._PAY_TERMS`. `_sel_opts` would have rendered nothing selected
    and the browser would then post the FIRST option.
    """
    from quotation import _PAY_TERMS
    import demo_data as DD

    terms = DD.BOQ_META["payment_terms"]
    assert terms not in _PAY_TERMS, "fixture no longer exercises this path"

    html = client.get("/boq/create?demo=1").get_data(as_text=True)
    block = re.search(r'<select id="payment_terms".*?</select>', html, re.S).group(0)
    selected = re.search(r"<option selected>(.*?)</option>", block).group(1)
    assert selected.startswith("Material Payment 50% Advance")


# ═══ CLASS: paper-only faults ══════════════════════════════════════════════

def test_each_section_table_has_its_own_colgroup(seeded, client):
    """
    Under `table-layout:fixed` the widths come from <col> if present and
    otherwise from the first row — where the area columns are one colspan cell.
    Without a colgroup a two-area section printed its quantity columns at 7mm.
    """
    bid = next(iter(STORE["boqs"]))
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    tables = re.findall(r'<table class="boq-table">(.*?)</table>', html, re.S)
    assert len(tables) == 3
    # A, B, C declare 2, 1 and 0 areas -> 13, 12 and 11 columns.
    for table, want in zip(tables, (13, 12, 11)):
        cg = re.search(r"<colgroup>(.*?)</colgroup>", table, re.S)
        assert cg, "section table without a colgroup"
        assert len(re.findall(r"<col[^>]*/>", cg.group(1))) == want


def test_colgroup_matches_the_header_column_count(seeded, client):
    from html.parser import HTMLParser

    bid = next(iter(STORE["boqs"]))
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)

    class Rows(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.cur, self.pending, self.i = [], None, {}, 0

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "tr":
                self.cur = self.pending.pop(self.i, 0)
            elif tag in ("td", "th") and self.cur is not None:
                cs = int(a.get("colspan", 1))
                self.cur += cs
                for r in range(1, int(a.get("rowspan", 1))):
                    self.pending[self.i + r] = self.pending.get(self.i + r, 0) + cs

        def handle_endtag(self, tag):
            if tag == "tr" and self.cur is not None:
                self.rows.append(self.cur)
                self.cur = None
                self.i += 1

    for table in re.findall(r'<table class="boq-table">(.*?)</table>', html, re.S):
        n_cols = len(re.findall(r"<col[^>]*/>",
                                re.search(r"<colgroup>(.*?)</colgroup>", table, re.S).group(1)))
        p = Rows()
        p.feed(table)
        assert set(p.rows) == {n_cols}, f"ragged: rows {sorted(set(p.rows))} vs {n_cols} cols"


def test_landscape_override_wins_the_cascade(seeded, client):
    bid = next(iter(STORE["boqs"]))
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert html.index("size:A4 landscape") > html.index("size:A4 portrait")


def test_multipage_print_rules_are_present(seeded, client):
    """A 97-line BOQ is several sheets; the bands have to repeat and rows must
    not be split down the middle."""
    bid = next(iter(STORE["boqs"]))
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert ".page-frame > thead { display:table-header-group; }" in html
    assert ".boq-table > thead { display:table-header-group; }" in html
    assert ".sec-head { break-after:avoid; page-break-after:avoid; }" in html
    assert "break-inside:avoid; page-break-inside:avoid" in html


def test_no_unscoped_print_breakpoint(seeded, client):
    """An unscoped max-width breakpoint fires on paper."""
    bid = next(iter(STORE["boqs"]))
    html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "@media screen and (max-width:760px)" in html
    assert not re.search(r"@media\s*\(max-width:\s*760px\)", html)


# ═══ CLASS: empty and edge states ═════════════════════════════════════════

def _bare_boq(sections, lines):
    import uuid

    bid = str(uuid.uuid4())
    STORE["boqs"][bid] = {
        "id": bid, "ref": "SF/BOQ/26-27/9999", "fy": "26-27", "date": "2026-06-15",
        "rev_no": 0, "project_name": "Edge", "site_location": "", "account_name": "A",
        "contact_person": "", "to": "A", "bill_gstin": "", "ship_same": True,
        "rate_basis_label": "Base Rate", "sections": sections, "line_items": lines,
        "supply_subtotal": 0.0, "install_subtotal": 0.0, "subtotal": 0.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }
    return bid


def _line(**kw):
    d = {"item_no": "1", "parent_item_no": "", "section": "A", "is_header": False,
         "description": "d", "remark": "", "unit": "Nos", "area_qty": {},
         "total_qty": 0.0, "supply_base_rate": None, "supply_escalation_pct": 0.0,
         "supply_rate": 0.0, "supply_amount": 0.0, "supply_hsn": "",
         "supply_gst_rate": 18.0, "install_base_rate": None,
         "install_escalation_pct": 0.0, "install_rate": 0.0, "install_amount": 0.0,
         "install_sac": "", "install_gst_rate": 18.0}
    d.update(kw)
    return d


@pytest.mark.parametrize("name,sections,lines", [
    ("no sections and no lines", [], []),
    ("section with zero lines", [{"code": "A", "title": "E", "areas": ["L0"]}], []),
    ("only the middle section has lines",
     [{"code": "A", "title": "a", "areas": []},
      {"code": "B", "title": "b", "areas": ["T1"]},
      {"code": "C", "title": "c", "areas": []}],
     [_line(section="B", area_qty={"T1": 2.0}, total_qty=2.0,
            supply_rate=10.0, supply_amount=20.0)]),
    ("every area quantity zero",
     [{"code": "A", "title": "a", "areas": ["L0", "L1"]}],
     [_line(area_qty={"L0": 0.0, "L1": 0.0}, supply_rate=100.0)]),
    ("a header row with no children",
     [{"code": "A", "title": "a", "areas": []}],
     [_line(is_header=True, description="clause only")]),
    ("a line whose section does not exist",
     [{"code": "A", "title": "a", "areas": []}],
     [_line(section="ZZ", supply_rate=5.0, total_qty=1.0, supply_amount=5.0)]),
])
def test_degenerate_boqs_still_render(seeded, client, name, sections, lines):
    """A hand-edited record must not be able to 500 a page."""
    bid = _bare_boq(sections, lines)
    assert client.get(f"/boq/view/{bid}").status_code == 200, name
    assert client.get("/boq/").status_code == 200, name


def test_a_spec_with_one_blank_variant_renders_everywhere(seeded, client):
    sp = spec.spec_by_code("HYD-FIREMANS-AXE")
    assert len(sp["variants"]) == 1 and sp["variants"][0]["label"] == ""
    for url in ("/spec/", f"/spec/view/{sp['id']}", f"/spec/edit/{sp['id']}",
                "/boq/create"):
        assert client.get(url).status_code == 200, url


def test_deleting_a_spec_leaves_the_boq_printable(seeded, client):
    bid = next(iter(STORE["boqs"]))
    for sid in list(STORE["specs"]):
        client.get(f"/spec/delete/{sid}")
    assert not STORE["specs"]
    assert client.get(f"/boq/view/{bid}").status_code == 200
    b = STORE["boqs"][bid]
    sup, ins, _t = boq.boq_totals(b)
    assert round(sup, 2) == 6177563.30 and round(ins, 2) == 3013750.00
    assert client.get("/boq/create").status_code == 200


# ═══ CLASS: rejected POSTs must keep the user's input ═════════════════════

def test_rejected_boq_post_keeps_everything(seeded, client):
    payload = {"sections": [{"code": "A", "title": "My Section", "areas": ["Roof"]}],
               "lines": [{"item_no": "7.7", "parent_item_no": "", "section": "A",
                          "is_header": False, "description": "A" * 1500,
                          "remark": "note", "unit": "Mtrs",
                          "area_qty": {"Roof": "12"}, "total_qty": "",
                          "supply_base_rate": "1000", "supply_escalation_pct": "15",
                          "supply_rate": "1150", "supply_hsn": "",
                          "supply_gst_rate": "18", "install_base_rate": "",
                          "install_escalation_pct": "", "install_rate": "",
                          "install_sac": "", "install_gst_rate": "18"}]}
    before = len(STORE["boqs"])
    r = client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "Kept Project",
        "site_location": "Kept Site", "rate_basis_label": "Kept Basis",
        "account_name": "", "bill_city": "Kept City", "notes": "Kept notes",
        "boq_json": json.dumps(payload)})
    assert r.status_code == 200
    assert len(STORE["boqs"]) == before
    html = r.get_data(as_text=True)
    for kept in ("Kept Project", "Kept Site", "Kept Basis", "Kept City", "Kept notes"):
        assert kept in html, kept
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\n", html, re.S).group(1))
    assert model["sections"][0]["areas"] == ["Roof"]
    assert len(model["lines"][0]["description"]) == 1500


def test_rejected_spec_post_keeps_the_variant_rows(seeded, client):
    r = client.post("/spec/add", data={
        "code": "", "title": "Kept Title", "category": "Valves",
        "spec_text": "B" * 1500, "supply_hsn": "73063090", "install_sac": "995462",
        "supply_gst_rate": "12", "install_gst_rate": "5",
        "var_label": ["100mm", "150mm"], "var_dimension": ["100", "150"],
        "var_dim_unit": ["mm", "mm"], "var_unit": ["Mtrs", "Mtrs"],
        "var_supply": ["111", "222"], "var_install": ["33", "44"]})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Kept Title" in html
    assert "B" * 1500 in html
    assert '<option value="Valves" selected>' in html
    # Slice off at the <template>, which holds a blank row with the same
    # field names and would otherwise be counted as a third.
    rows = html.split('id="var-rows"')[1].split('<template id="var-tpl">')[0]
    assert rows.count('name="var_label"') == 2
    for v in ("100mm", "150mm", "111", "222", "33", "44"):
        assert f'value="{v}"' in rows, v


def test_rates_are_handed_back_as_typed(seeded, client):
    """`111` must not come back as `111.0` — a rejected form returns what was
    typed, and reformatting it is a small breach of the same contract."""
    r = client.post("/spec/add", data={
        "code": "", "title": "t", "category": "Other", "spec_text": "x",
        "supply_hsn": "", "install_sac": "", "supply_gst_rate": "18",
        "install_gst_rate": "18", "var_label": ["100mm"], "var_dimension": ["100"],
        "var_dim_unit": ["mm"], "var_unit": ["Mtrs"],
        "var_supply": ["111"], "var_install": ["977.5"]})
    html = r.get_data(as_text=True)
    assert 'name="var_supply" value="111"' in html
    assert 'name="var_install" value="977.5"' in html
    assert "111.0" not in html


# ═══ BUG 3: the demo has to be loadable into the form ═════════════════════

def test_demo_data_loads_into_the_create_form(seeded, client):
    html = client.get("/boq/create?demo=1").get_data(as_text=True)
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\n", html, re.S).group(1))
    assert [s["code"] for s in model["sections"]] == ["A", "B", "C"]
    assert len(model["lines"]) == 97
    assert sum(1 for l in model["lines"] if l["is_header"]) == 10
    assert "demo-banner" in html
    assert 'value="Sify Bangalore"' in html


def test_loading_the_demo_writes_nothing(seeded, client):
    before = dict(STORE["boqs"])
    client.get("/boq/create?demo=1")
    assert STORE["boqs"] == before


def test_the_demo_round_trips_through_the_form(seeded, client):
    """
    Load it, post it back, and the schedule must come out identical. This is
    the whole point of the feature: what the form loads is what it saves.
    """
    html = client.get("/boq/create?demo=1").get_data(as_text=True)
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\n", html, re.S).group(1))

    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={
        "date": "2026-06-15", "rev_no": "0", "project_name": "Sify Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "rate_basis_label": "Mohali Rates",
        "boq_json": json.dumps(model)})
    assert r.status_code == 302

    new = [b for k, b in STORE["boqs"].items() if k not in before][0]
    assert len(new["line_items"]) == 97
    assert sum(1 for li in new["line_items"] if li["is_header"]) == 10
    sup, ins, _t = boq.boq_totals(new)
    assert round(sup, 2) == 6177563.30
    assert round(ins, 2) == 3013750.00
    for code, want in (("A", (483764.50, 311350.00)),
                       ("B", (5659023.80, 2357400.00)),
                       ("C", (34775.00, 345000.00))):
        got = boq.section_totals(new, code)
        assert (round(got[0], 2), round(got[1], 2)) == want, code
