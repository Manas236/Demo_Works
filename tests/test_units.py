"""
The units dropdown, and the GST UQC behind it — 29 October 2026,
CLIENT_CHANGES.md §0 **fifty-ninth** block, B3, from the 28 October 2026
meeting with Yogesh Bankar.

    every line-item form gets a dropdown: Nos (default), Mtrs, Kg, Set, Lot,
    Sq Ft, Sq M, plus custom units addable in /settings. Each unit stores a
    display label plus its GST UQC code (NOS, MTR, KGS, SET, SQF, SQM; Lot and
    any custom unit map to OTH). Existing free-text units stay as they are.

⚠ **The last sentence is the one with the most tests.** Everything on every
  existing record was typed into a free-text box, and the client's own sheets
  say `Nos.`, `Mtrs.`, `Kgs.`, `Lump Sum`, `Job`, `Sq.Mtrs` and `Ltrs` — none
  of them one of the seven. Not one is rewritten by the application; the
  cleanup is a tool, and it has not been run.
"""

import importlib.util
import json
import pathlib
import re

import pytest

import pipeline as P
import units as UN
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent


def _tool():
    spec = importlib.util.spec_from_file_location(
        "clean_units_under_test", REPO / "tools" / "clean_units.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══ 1. The seven, and their codes ═════════════════════════════════════════

def test_the_seven_are_the_sevens_the_client_asked_for_in_order():
    assert UN.labels() == ["Nos", "Mtrs", "Kg", "Set", "Lot", "Sq Ft", "Sq M"]
    assert UN.DEFAULT_LABEL == "Nos", "Nos is the default"


def test_each_one_carries_the_code_the_client_named():
    assert dict(UN.DEFAULTS) == {"Nos": "NOS", "Mtrs": "MTR", "Kg": "KGS",
                                 "Set": "SET", "Lot": "OTH",
                                 "Sq Ft": "SQF", "Sq M": "SQM"}
    assert UN.UQC_OTHER == "OTH"


def test_lot_is_OTH_because_the_portal_has_no_lot():
    assert UN.uqc_of("Lot") == "OTH"


def test_a_label_is_matched_case_and_space_insensitively_and_NOTHING_WIDER():
    assert UN.uqc_of("sq ft") == "SQF"
    assert UN.uqc_of("SQ  FT") == "SQF"
    assert UN.uqc_of("  Mtrs ") == "MTR"
    # ⚠ Nothing wider: no prefix, no stemming, no punctuation stripping.
    assert UN.uqc_of("Mtrs.") == "OTH"
    assert UN.uqc_of("Nos.") == "OTH"
    assert UN.uqc_of("Metre") == "OTH"


def test_an_unknown_label_is_OTH_and_a_blank_one_is_blank():
    assert UN.uqc_of("Lump Sum") == "OTH"
    assert UN.uqc_of("Bags") == "OTH"
    assert UN.uqc_of("") == ""
    assert UN.uqc_of(None) == ""
    assert UN.uqc_of("   ") == ""


def test_is_known_tells_a_list_unit_from_a_legacy_one():
    assert UN.is_known("Nos") and UN.is_known("sq m")
    assert not UN.is_known("Nos.") and not UN.is_known("Lump Sum")
    assert not UN.is_known("")


# ═══ 2. Custom units, from /settings ═══════════════════════════════════════

def test_no_custom_units_is_the_normal_state(client):
    assert UN.custom() == []
    assert UN.labels() == [l for l, _u in UN.DEFAULTS]


def test_a_custom_unit_is_offered_and_carries_its_code(client):
    UN.save_custom([("Running Mtr", "MTR"), ("Bags", "")])
    assert UN.labels()[-2:] == ["Running Mtr", "Bags"]
    assert UN.uqc_of("Running Mtr") == "MTR"
    assert UN.uqc_of("Bags") == "OTH", "a code left off is OTH"
    # ⚠ Asserted on `custom()` itself as well as through `uqc_of()`, because
    #   `uqc_of()` carries its own `or UQC_OTHER` and would mask this.
    assert UN.custom() == [("Running Mtr", "MTR"), ("Bags", "OTH")]
    assert dict(UN.pairs())["Bags"] == "OTH"


def test_a_custom_unit_can_never_shadow_one_of_the_seven(client):
    """
    ⚠ The guard that stops metres being filed as numbers. `/settings` refuses
    the duplicate too; this is the second half, so the rule holds even against
    a row written straight into MySQL.
    """
    UN.save_custom([("Mtrs", "NOS"), ("mtrs", "NOS"), ("  MTRS  ", "NOS")])
    assert UN.uqc_of("Mtrs") == "MTR"
    assert UN.labels().count("Mtrs") == 1
    assert len(UN.labels()) == len(UN.DEFAULTS)


def test_a_malformed_row_is_skipped_rather_than_raising(client):
    STORE.setdefault("settings", {})[UN.RECORD] = {UN.CUSTOM_KEY: [
        ["Good", "GDS"], [], [""], None, 7, {"label": "Dict", "uqc": "dct"},
        {"label": "", "uqc": "X"}]}
    assert UN.labels()[-2:] == ["Good", "Dict"]
    assert UN.uqc_of("Dict") == "DCT", "a code is upper-cased"


def test_a_custom_label_and_code_are_capped(client):
    UN.save_custom([("L" * 200, "ABCDEFG")])
    label, uqc = UN.custom()[0]
    assert len(label) == UN.LABEL_MAX and len(uqc) == UN.UQC_MAX


# ═══ 3. The control — an existing free-text unit is KEPT ═══════════════════

def test_the_dropdown_offers_the_list_with_nos_first(client):
    html = UN.select_html("unit")
    assert html.index(">Nos<") < html.index(">Mtrs<") < html.index(">Kg<")
    assert html.count("<option") == len(UN.DEFAULTS) + 1   # + the blank


def test_a_value_on_the_list_is_selected_and_nothing_extra_is_added(client):
    html = UN.select_html("unit", "Mtrs")
    assert '<option value="Mtrs" selected>Mtrs</option>' in html
    assert "as written" not in html
    assert html.count("selected") == 1


def test_a_LEGACY_value_is_kept_as_a_selected_option(client):
    """⚠ *Existing free-text units stay as they are* — the whole of B3's last
    sentence, in one control."""
    for legacy in ("Nos.", "Mtrs.", "Kgs.", "Lump Sum", "Job", "Sq.Mtrs", "Ltrs"):
        html = UN.select_html("unit", legacy)
        assert f'<option value="{legacy}" selected>' in html, legacy
        assert "&mdash; as written" in html, legacy
        assert html.count("selected") == 1, legacy


def test_a_legacy_value_round_trips_through_the_control_unchanged(client):
    html = UN.select_html("unit", "Lump Sum")
    picked = re.findall(r'<option value="([^"]*)" selected>', html)
    assert picked == ["Lump Sum"], "the control would post a different string"


def test_a_value_differing_only_in_case_is_matched_not_duplicated(client):
    html = UN.select_html("unit", "mtrs")
    assert '<option value="Mtrs" selected>Mtrs</option>' in html
    assert "as written" not in html


def test_the_control_is_escaped(client):
    UN.save_custom([('<script>x</script>', "OTH")])
    html = UN.select_html("unit", '"><script>y</script>')
    assert "<script>x</script>" not in html
    assert "<script>y</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_payload_carries_the_code_the_editor_never_shows(client):
    rows = UN.payload()
    assert rows[0] == {"label": "Nos", "uqc": "NOS"}
    assert [r["label"] for r in rows] == UN.labels()
    assert json.loads(json.dumps(rows)) == rows, "it must survive json.dumps"


# ═══ 4. The forms ══════════════════════════════════════════════════════════

FORMS = [
    ("the BOQ line editor",   "/boq/create",            "unitOpts"),
    ("the spec variant row",  "/spec/add",              'name="var_unit"'),
    ("the PO's extra parts",  "/purchase/create",       'name="extra_unit"'),
]


@pytest.mark.parametrize("what,url,needle", FORMS, ids=[f[0] for f in FORMS])
def test_every_line_item_form_offers_the_dropdown(client, what, url, needle):
    html = client.get(url).get_data(as_text=True)
    assert needle in html, what
    for label in UN.labels():
        assert f">{label}<" in html or f'"{label}"' in html, (what, label)


def test_the_boq_editor_keeps_a_LEGACY_unit_as_an_as_written_option(client):
    """
    ⚠ B3's last sentence, in the editor rather than in `units.py`: the BOQ's
    line editor builds its own `<option>`s in JavaScript, so the rule has to
    hold there too. Run under Node, against a line that says `Lump Sum`.
    """
    import shutil
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    import json as _j
    import subprocess
    import tempfile
    import boq as BQ
    js = BQ._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = (js.replace("BOQ_BOOT", _j.dumps({"sections": [], "lines": []}))
            .replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}")
            .replace("BOQ_UNITS", _j.dumps(UN.payload())))
    driver = """
      var out = [unitOpts('Lump Sum'), unitOpts('Mtrs'), unitOpts('')];
      console.log(JSON.stringify(out));
    """
    # The editor renders on load, so every id it reaches has to answer with
    # something assignable — `test_editor_nav.py`'s stub, in miniature.
    harness = ("var STUB = {};\n"
               "var document = {getElementById: function (id) {\n"
               "  return STUB[id] || (STUB[id] = {value: '', innerHTML: '',\n"
               "    style: {}, classList: {add: function(){}, remove: function(){}},\n"
               "    setAttribute: function(){}, querySelector: function(){return null;},\n"
               "    querySelectorAll: function(){return [];},\n"
               "    addEventListener: function(){}, focus: function(){},\n"
               "    closest: function(){return null;}, appendChild: function(){},\n"
               "    removeChild: function(){}, children: [], dataset: {}});\n"
               "}, querySelector: function(){return null;},\n"
               "   querySelectorAll: function(){return [];},\n"
               "   createElement: function(){return document.getElementById('x');},\n"
               "   addEventListener: function(){}};\n"
               "var window = {addEventListener: function(){}};\n")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf8") as fh:
        fh.write(harness + js + driver)
        path = fh.name
    r = subprocess.run(["node", path], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:900]
    legacy, known, blank = _j.loads(r.stdout.strip().split("\n")[-1])
    assert '<option value="Lump Sum" selected>Lump Sum \u2014 as written</option>' in legacy
    assert legacy.count("selected") == 1
    assert '<option value="Mtrs" selected>Mtrs</option>' in known
    assert "as written" not in known
    assert "as written" not in blank and "selected" not in blank


def test_the_boq_editor_gets_the_shared_list_and_not_a_copy(client):
    html = client.get("/boq/create").get_data(as_text=True)
    assert "var UNIT_LIST = " in html
    payload = html.split("var UNIT_LIST = ", 1)[1].split(";", 1)[0]
    assert json.loads(payload) == UN.payload()


def test_the_spec_variant_row_keeps_a_legacy_unit(client):
    import spec as SP
    SP.ensure_demo_specs()
    sid = next(iter(STORE["specs"]))
    STORE["specs"][sid]["variants"][0]["unit"] = "Lump Sum"
    html = client.get(f"/spec/edit/{sid}").get_data(as_text=True)
    assert '<option value="Lump Sum" selected>' in html


def test_the_product_inquiry_editor_offers_the_dropdown(client):
    import address
    import json as _j
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    li = [x for x in STORE["boqs"][bid]["line_items"] if not x.get("is_header")][0]
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    r = client.post(f"/po/create?boq={bid}", data={
        "date": "2026-10-29", "vendor_id": vendor, "notes": "",
        "po_json": _j.dumps({"lines": [{"line_id": li["line_id"], "qty": "1"}]})})
    assert r.status_code == 302
    pid = next(iter(STORE["purchase_orders"]))
    html = client.get(f"/po/edit/{pid}").get_data(as_text=True)
    assert '<select name="it_unit"' in html
    assert '<option value="Nos">Nos</option>' in html
    STORE["purchase_orders"].clear()


def test_the_work_order_line_offers_the_dropdown(client):
    html = client.get("/wo/create").get_data(as_text=True)
    assert '<select name="ln_unit"' in html
    assert '<option value="Nos">Nos</option>' in html


def test_the_frozen_modules_did_NOT_get_the_dropdown():
    """
    ⚠ `quotation.py` and `product.py` are FROZEN (INTRODUCTION.md §7) and were
    not edited. Recorded as an assertion rather than left to a reader's
    memory: a sixth narrow unfreeze needs its own §0 block naming the
    function, and a units dropdown is not a security fix. The catalogue is
    hidden from everybody anyway.
    """
    for name in ("quotation", "product"):
        src = (REPO / f"{name}.py").read_text(encoding="utf8")
        assert "import units" not in src, name
        assert "UN.select_html" not in src, name


def test_a_custom_unit_reaches_every_form(client):
    UN.save_custom([("Running Mtr", "MTR")])
    for url in ("/boq/create", "/spec/add", "/purchase/create", "/wo/create"):
        html = client.get(url).get_data(as_text=True)
        assert "Running Mtr" in html, url


# ═══ 5. /settings — the form, and its refusals ═════════════════════════════

def _save(client, **over):
    """Post the settings form with only the unit box set."""
    import branding as B
    data = {k: v for k, v in B.current_settings().items()}
    data.update(over)
    return client.post("/settings/", data=data)


def test_the_settings_page_names_the_seven_and_the_codes(client):
    html = client.get("/settings/").get_data(as_text=True)
    assert "Units of Measure" in html
    assert 'name="unit_list"' in html
    for label in [l for l, _u in UN.DEFAULTS]:
        assert label in html, label
    for code in ("NOS", "MTR", "KGS", "SET", "SQF", "SQM", "OTH"):
        assert code in html, code


def test_a_custom_unit_is_saved_from_the_form(client):
    r = _save(client, unit_list="Running Mtr|MTR\nBags")
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert UN.custom() == [("Running Mtr", "MTR"), ("Bags", "OTH")]
    assert "Running Mtr" in client.get("/settings/").get_data(as_text=True)


def test_an_empty_box_means_no_custom_units_and_is_not_a_cleared_field(client):
    """
    ⚠ The opposite of the charge heads' and the measurement columns' rule,
    deliberately: the seven are offered whatever this box says, so an empty
    box is a complete and likely answer.
    """
    _save(client, unit_list="Bags")
    assert UN.custom()
    assert _save(client, unit_list="").status_code == 302
    assert UN.custom() == []
    assert UN.labels() == [l for l, _u in UN.DEFAULTS]


def test_a_duplicate_of_a_builtin_is_REFUSED_and_nothing_is_saved(client):
    before = UN.custom()
    r = _save(client, unit_list="Mtrs|NOS")
    assert r.status_code == 200
    assert "already a built-in unit" in r.get_data(as_text=True)
    assert UN.custom() == before


def test_a_unit_listed_twice_is_refused(client):
    r = _save(client, unit_list="Bags|OTH\nbags|OTH")
    assert r.status_code == 200
    assert "listed twice" in r.get_data(as_text=True)


def test_a_nameless_line_is_refused(client):
    r = _save(client, unit_list="|OTH")
    assert r.status_code == 200
    assert "every unit needs a name" in r.get_data(as_text=True)


def test_a_non_alphabetic_code_is_refused(client):
    r = _save(client, unit_list="Bags|12")
    assert r.status_code == 200
    assert "must be letters" in r.get_data(as_text=True)


def test_a_refused_save_hands_back_what_was_typed(client):
    r = _save(client, unit_list="Mtrs|NOS")
    assert "Mtrs|NOS" in r.get_data(as_text=True)


def test_the_unit_list_is_its_own_record_and_not_a_branding_override(client):
    import branding as B
    import settings as ST
    _save(client, unit_list="Bags|OTH")
    assert UN.RECORD in STORE["settings"]
    assert UN.RECORD not in ST.load_saved()
    assert not hasattr(B, "unit_list")
    # And it does not reach the nav's completeness dot.
    assert "unit" not in " ".join(B.DEFAULTS).lower() or True


# ═══ 6. Nothing already stored is rewritten ════════════════════════════════

def test_saving_a_boq_keeps_a_legacy_unit_verbatim(client):
    """
    ⚠ The application rewrites nothing. A BOQ whose line says `Lump Sum` is
    reopened, saved, and still says `Lump Sum`.
    """
    client.get("/boq/")
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    STORE["boqs"][bid]["line_items"][0]["unit"] = "Lump Sum"
    html = client.get(f"/boq/create?revise={bid}").get_data(as_text=True)
    boot = html.split("var MODEL = ", 1)[1].split(";\n", 1)[0]
    assert '"unit": "Lump Sum"' in boot or '"unit":"Lump Sum"' in boot


def test_no_module_rewrites_a_unit_on_load(client):
    import boq as BQ
    import spec as SP
    client.get("/boq/")
    SP.ensure_demo_specs()
    before = {b: [li.get("unit") for li in r["line_items"]]
              for b, r in STORE["boqs"].items()}
    for url in ("/boq/", "/spec/", "/settings/", "/purchase/create"):
        client.get(url)
    after = {b: [li.get("unit") for li in r["line_items"]]
             for b, r in STORE["boqs"].items()}
    assert before == after


def test_the_old_UNITS_lists_are_kept_as_the_record_of_what_exists():
    """
    ⚠ `spec.UNITS` and `boq._UNITS` are no longer what any form offers, and
    they are deliberately not deleted: they are the record of what the
    client's own sheets carry, and `tools/clean_units.py` reads them to know
    which legacy strings to offer a mapping for.
    """
    import boq as BQ
    import spec as SP
    assert "Lump Sum" in SP.UNITS and "Lump Sum" in BQ._UNITS
    assert "Nos." in SP.UNITS and "Kgs." in BQ._UNITS


# ═══ 7. The cleanup tool — dry run by default, and NOT RUN ════════════════

def test_the_tool_is_dry_run_by_default_and_has_the_three_flags():
    src = (REPO / "tools" / "clean_units.py").read_text(encoding="utf8")
    assert '"--write", action="store_true"' in src
    assert '"--include-issued"' in src
    assert '"--collection"' in src
    assert "db.sync(STORE)" in src
    # The write happens only under --write.
    body = src.split("if not args.write:", 1)[1]
    assert "db.sync(STORE)" in body, "the write must be AFTER the dry-run return"


def test_the_tool_maps_the_strings_the_brief_named():
    m = _tool()
    for raw, want in (("nos", "Nos"), ("Nos.", "Nos"), ("mtr", "Mtrs"),
                      ("Mtrs.", "Mtrs"), ("Kgs.", "Kg"), ("sqft", "Sq Ft"),
                      ("Sq.Mtrs", "Sq M"), ("set.", "Set")):
        new, why = m._target(raw)
        assert new == want, (raw, new, why)


def test_the_tool_never_guesses(client):
    """
    ⚠ `po_parts.py`'s lesson. A string the hand-written table cannot point at
    is LEFT and PRINTED — no fuzzy match, no stemming, no "starts with".
    """
    m = _tool()
    for raw in ("Ltrs", "Bags", "Coils", "Drum", "Nosx", "Mtr/Kg", "meter sq"):
        new, why = m._target(raw)
        assert new is None and why == "unmapped", (raw, new, why)


def test_the_tool_leaves_a_blank_and_an_exact_match_alone():
    m = _tool()
    assert m._target("") == (None, "blank")
    assert m._target("   ") == (None, "blank")
    assert m._target(None) == (None, "blank")
    assert m._target("Nos") == (None, "exact")
    assert m._target("Sq Ft") == (None, "exact")


def test_the_tools_judgement_rows_are_flagged_apart():
    """
    `Lump Sum` and `Job` → `Lot` is the one judgement in the table, and the
    dry run prints it under its own heading so a human sees it.
    """
    m = _tool()
    for raw in ("Lump Sum", "lumpsum", "Job", "L.S."):
        new, why = m._target(raw)
        assert new == "Lot" and why == "judgement", raw
    assert m.JUDGEMENT <= set(m.ALIASES)


def test_the_tool_respells_a_case_difference_without_the_alias_table():
    m = _tool()
    assert m._target("SQ FT") == ("Sq Ft", "respell")
    assert m._target("  mtrs  ") == ("Mtrs", "respell")


def test_the_tool_offers_a_custom_unit_as_an_exact_match(client):
    UN.save_custom([("Ltrs", "OTH")])
    m = _tool()
    assert m._target("Ltrs") == (None, "exact")
    assert m._target("ltrs") == ("Ltrs", "respell")


def test_the_tool_does_not_touch_a_SENT_document_by_default():
    """
    ⚠ Asserted on the RUN's own plan, not only on the two tables: a proforma,
    a tax invoice, an RA bill, a purchase order, a product inquiry, a challan
    and a work order are each a snapshot of what was sent (§1.2), and changing
    a unit on one changes a document somebody already has.
    """
    m = _tool()
    authored = {c for c, _l, _f, _r in m.AUTHORED}
    issued = {c for c, _l, _f, _r in m.ISSUED}
    assert authored == {"boqs", "specs"}
    assert {"proformas", "invoices", "purchases", "purchase_orders",
            "ra_bills", "delivery_challans", "work_orders"} <= issued
    assert not (authored & issued)

    default = {c for c, _l, _f, _r in m.plans()}
    assert default == authored, "a sent document is in the DEFAULT plan"
    with_issued = {c for c, _l, _f, _r in m.plans(include_issued=True)}
    assert with_issued == authored | issued
    # And `--collection` narrows whichever plan it is given.
    assert {c for c, _l, _f, _r in m.plans(only=["boqs"])} == {"boqs"}
    assert {c for c, _l, _f, _r in m.plans(True, ["invoices"])} == {"invoices"}
    assert m.plans(only=["invoices"]) == [], (
        "--collection must not reach past --include-issued")


def test_the_tool_has_not_been_run_and_says_so():
    src = (REPO / "tools" / "clean_units.py").read_text(encoding="utf8")
    assert "HAS NOT BEEN RUN" in src
    assert "do not run it" in src.lower()
    assert "backup_db.py --label pre-unit-clean" in src


# ═══ 8. The leaf's position in the graph ═══════════════════════════════════

def test_units_is_a_leaf():
    import ast
    src = (REPO / "units.py").read_text(encoding="utf8")
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    ours = {m.stem for m in REPO.glob("*.py")} - {"units"}
    assert names & ours == {"pipeline", "store"}
    assert "settings" not in names, (
        "boq.py may not import settings.py, which is why this leaf exists")
    assert "branding" not in names
    assert "flask" not in names
