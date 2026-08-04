"""
The BOQ picker's fill rules, executed — through the rendered controls.

WHY THIS FILE WAS REWRITTEN
---------------------------
The previous version passed while the feature was broken in the browser. Three
reasons, all of them worth remembering because they are how any JS harness
lies:

1. **It called the functions directly.** `fillFromVariant(0, '150 mm dia')`
   exercises a function; it does not exercise the `<select onchange=…>` that
   is supposed to call it, nor the option `value` the DOM would actually hand
   over. A handler could be unwired, mis-argumented or never rendered and the
   test would not notice. This version pulls the `onchange` attribute out of
   the **rendered row** and fires it with `this.value` set to a real option
   value, so the wiring is under test too.

2. **Every case started from a fresh `blankLine()`.** The old fill rule was
   "write only if the box is empty", so a blank row was the one input where it
   worked. The reported bug — pick a spec, pick a variant, then change the spec
   — needs *two* picks to show up, and nothing tested two. Every test below
   that matters now runs a sequence.

3. **Each case ran in its own Node process**, so no state survived between
   actions and index-keyed bookkeeping could not desync. `delLine` corrupting
   the row→spec map was invisible for exactly that reason.

The rule under test is stated in full above the picker in `boq.py`: a pick
overwrites **empty** and **auto**, and never overwrites **typed**.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")

# Injected into the harness: fires a rendered control the way a browser would.
_DRIVER = """
function rowHtml(i) {
  var parts = STUB['line-editor'].innerHTML.split('<div class="line-card');
  if (!parts[i + 1]) throw new Error('no row ' + i + ' rendered');
  return parts[i + 1];
}

/* Pull the onchange attribute off the rendered <select> for row `i` and run
   it with `this.value` set to `value` — which is what the browser does. If the
   control was never rendered, or its handler is not wired, this throws. */
function fireSelect(i, which, value) {
  var html = rowHtml(i);
  var re = which === 'spec' ? /onchange="(fillFromSpec\\([^"]*)"/
                            : /onchange="(fillFromVariant\\([^"]*)"/;
  var m = re.exec(html);
  if (!m) throw new Error('row ' + i + ' has no wired ' + which + ' select');
  var code = m[1].replace(/&quot;/g, '"').replace(/this\\./g, 'SELF.');
  var SELF = { value: value };
  /* Direct eval, not `new Function`: a browser resolves an inline handler
     against the global scope, and on the real page these functions ARE global
     because _BOQ_JS is a plain <script> block. Node module-scopes them, which
     is an artifact of running the file here — direct eval sees the same scope
     chain the page would. */
  eval(code);
}

/* The option values the rendered variant dropdown is offering. */
function variantValues(i) {
  var html = rowHtml(i);
  var sel = /<select onchange="fillFromVariant[^>]*>([\\s\\S]*?)<\\/select>/.exec(html);
  if (!sel) return null;
  var out = [], re = /<option value="([^"]*)"/g, m;
  while ((m = re.exec(sel[1])) !== null) out.push(m[1]);
  return out;
}

/* Open a row by firing its rendered summary toggle. A collapsed row has no
   controls at all — that is the point of the collapse — so anything driving a
   control has to open the row first, exactly as a user would. */
function openLine(i) {
  if (MODEL.lines[i]._open) return;
  var m = new RegExp('onclick="(toggleLine\\\\(' + i + '\\\\))"')
            .exec(STUB['line-editor'].innerHTML);
  if (!m) throw new Error('no rendered toggle for row ' + i);
  eval(m[1]);
}

/* Type into a field, the way an oninput handler would. */
function typeInto(i, key, value) { setLine(i, key, value); }

function dump() { console.log(JSON.stringify(MODEL.lines)); }
function dumpLine(i) { console.log(JSON.stringify(MODEL.lines[i])); }
"""


def _session(script: str):
    """
    Run a SEQUENCE of actions against the page's real JS in one process.

    One process, so state carries across actions — which is the only way a
    desync bug can surface.
    """
    import boq

    payload = boq._spec_catalog_json()
    harness = (
        "var BOQ_SPECS_JSON = " + payload + ";\n"
        "var STUB = { 'bulk-spec': {value:'', innerHTML:''}, "
        "'bulk-section': {value:'A', innerHTML:''}, "
        "'line-editor': {innerHTML:''}, 'sec-editor': {innerHTML:''}, "
        "'boq_json': {value:''} };\n"
        "var document = { body: {}, getElementById: function(id) "
        "{ return STUB[id] || null; } };\n"
        "var window = { scrollTo: function(){} };\n"
    )
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = js.replace("BOQ_SPECS", "BOQ_SPECS_JSON")
    js = js.replace("BOQ_BOOT", json.dumps(
        {"sections": [{"code": "A", "title": "Sprinklers", "areas": ["L0"]}],
         "lines": []}))
    js = js.replace("BOQ_ADDR", "{}")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf8") as fh:
        fh.write(harness + js + _DRIVER + "\n" + script)
        path = fh.name
    try:
        out = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=30, encoding="utf8")
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture()
def seeded(client):
    client.get("/boq/")
    return client


def _sid(code):
    import boq
    return [k for k, v in json.loads(boq._spec_catalog_json()).items()
            if v["code"] == code][0]


PIPE = "PIPE-MS-C-1239-SPR"      # 8 sized variants
PANEL = "PNL-LT-FIRE-BOARD"      # 2 sized variants
AXE = "HYD-FIREMANS-AXE"         # unsized
PUMP = "PMP-ELEC-END-SUCT"       # 4 variants with MULTI-LINE labels


# ═══ The wiring itself ═════════════════════════════════════════════════════

def test_both_selects_are_rendered_and_wired(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        var html = rowHtml(0);
        console.log(JSON.stringify({{
          hasSpecHandler: /onchange="fillFromSpec\\(0,this\\.value\\)"/.test(html),
          hasVariantHandler: /onchange="fillFromVariant\\(0,this\\.value\\)"/.test(html),
          variantValues: variantValues(0)
        }}));
    """)
    assert res["hasSpecHandler"], "the spec select is not wired to fillFromSpec"
    assert res["hasVariantHandler"], "the variant select is not wired"
    # A blank prompt plus one option per variant, carrying INDEXES.
    assert res["variantValues"] == ["", "0", "1", "2", "3", "4", "5", "6", "7"]


def test_multiline_variant_labels_are_selectable(seeded):
    """
    Five seeded labels are multi-line pump specifications. Matching those back
    by string through an HTML attribute is fragile; options carry the index.
    """
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PUMP)}');
        fireSelect(0, 'variant', '2');
        dumpLine(0);
    """)
    assert res["_variant"] == 2
    assert res["description"].startswith("Sprinkler Jockey Pump")
    assert res["unit"] == "Nos."


# ═══ A single pick on a blank row ══════════════════════════════════════════

def test_spec_fills_text_and_tax_classification(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        dumpLine(0);
    """)
    assert len(res["description"]) > 1000
    assert res["supply_hsn"] == "73063090"
    assert res["install_sac"] == "995462"
    assert res["supply_gst_rate"] == "18"
    assert res["install_gst_rate"] == "18"
    assert res["unit"] == "", "unit lives on the variant, not the spec"


def test_variant_fills_unit_and_both_base_rates(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '0');
        dumpLine(0);
    """)
    assert res["unit"] == "Mtrs."
    assert res["supply_base_rate"] == "1760"
    assert res["install_base_rate"] == "1200"
    assert res["description"] == "150mm dia     ISI"


def test_unsized_spec_applies_its_variant_immediately(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(AXE)}');
        dumpLine(0);
    """)
    assert res["unit"] == "Nos."
    assert "firemans axe" in res["description"]


# ═══ RE-SELECTION — the case the old harness never ran ═════════════════════

def test_changing_the_spec_replaces_everything_it_filled(seeded):
    """
    THE REPORTED BUG. Pick pipe, pick a size, then change to the fire panel:
    the row must not keep the pipe's description and unit.
    """
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '0');
        fireSelect(0, 'spec', '{_sid(PANEL)}');
        dumpLine(0);
    """)
    assert res["description"].startswith("Design, Fabrication, Supply")
    assert "150mm dia" not in res["description"]
    assert res["supply_hsn"] == "85371000"          # panel, not pipe
    # Unit and base rates belonged to a variant of the OLD spec.
    assert res["unit"] == ""
    assert res["supply_base_rate"] == ""
    assert res["install_base_rate"] == ""
    assert res["_variant"] is None


def test_choosing_a_second_variant_replaces_the_first(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '0');
        fireSelect(0, 'variant', '3');
        dumpLine(0);
    """)
    assert res["description"] == "65mm dia     ISI"
    assert res["supply_base_rate"] == "750"
    assert res["install_base_rate"] == "700"


def test_a_full_reselection_cycle_lands_on_the_last_choice(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '2');
        fireSelect(0, 'spec', '{_sid(PANEL)}');
        fireSelect(0, 'variant', '1');
        fireSelect(0, 'spec', '{_sid(AXE)}');
        dumpLine(0);
    """)
    assert "firemans axe" in res["description"]
    assert res["unit"] == "Nos."
    assert res["supply_hsn"] == "84241000"


# ═══ Typed values are never overwritten ════════════════════════════════════

def test_typed_values_survive_every_later_pick(seeded):
    res = _session(f"""
        addLine();
        typeInto(0, 'unit', 'Rmt');
        typeInto(0, 'supply_base_rate', '999');
        typeInto(0, 'description', 'our own wording');
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '0');
        fireSelect(0, 'spec', '{_sid(PANEL)}');
        dumpLine(0);
    """)
    assert res["unit"] == "Rmt"
    assert res["supply_base_rate"] == "999"
    assert res["description"] == "our own wording"
    # …while the fields the user never touched still follow the picker.
    assert res["supply_hsn"] == "85371000"


def test_typing_after_a_pick_pins_the_value(seeded):
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '0');
        typeInto(0, 'supply_base_rate', '1850');
        fireSelect(0, 'variant', '1');
        dumpLine(0);
    """)
    assert res["supply_base_rate"] == "1850", "an edited rate was overwritten"
    assert res["description"] == "100mm dia     ISI", "the un-edited field should follow"


def test_a_rate_the_variant_does_not_carry_is_left_alone(seeded):
    """24.a's base rate is "-" in the source — negotiated directly, so there is
    nothing to suggest and the box stays empty rather than gaining a zero."""
    res = _session(f"""
        addLine();
        fireSelect(0, 'spec', '{_sid("PIPE-MS-C-1239-AG")}');
        fireSelect(0, 'variant', '0');
        dumpLine(0);
    """)
    assert res["supply_base_rate"] == ""
    assert res["unit"] == "Mtrs"


# ═══ State must belong to the row, not to its position ════════════════════

def test_deleting_a_row_does_not_shift_the_others_spec(seeded):
    """
    `PICK` used to be keyed by array index, so deleting a line left every row
    below it showing the previous row's spec.
    """
    res = _session(f"""
        addLine();
        addLine();
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(1, 'spec', '{_sid(PANEL)}');
        delLine(0);
        console.log(JSON.stringify({{
          spec: SPECS[MODEL.lines[0]._spec].code,
          desc: MODEL.lines[0].description.slice(0, 28)
        }}));
    """)
    assert res["spec"] == PANEL
    assert res["desc"].startswith("Design, Fabrication")


def test_picker_state_is_posted_but_never_reaches_the_record(seeded, client):
    """
    `_spec` / `_variant` / `_auto` are UI bookkeeping, and a BOQ line has no
    spec_id. They ARE posted, deliberately: stripping them in the browser would
    also throw them away on a rejected POST, and the user would get their input
    back with the picker's typed/auto memory wiped. The record is kept clean on
    the SERVER instead — `_clean_lines()` builds a fresh dict from named keys,
    so an underscore key cannot get in whatever the browser sends.
    """
    import json as _json

    from store import STORE

    res = _session(f"""
        addLine();
        typeInto(0, 'item_no', '4.1');
        typeInto(0, 'total_qty', '4');
        fireSelect(0, 'spec', '{_sid(PIPE)}');
        fireSelect(0, 'variant', '0');
        saveJSON();
        console.log(STUB['boq_json'].value);
    """)
    line = res["lines"][0]
    assert line["_spec"] and line["_variant"] == 0 and line["_auto"]
    assert line["description"] == "150mm dia     ISI"
    assert line["supply_base_rate"] == "1760"

    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "P", "account_name": "A",
        "boq_json": _json.dumps(res)})
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    new = [b for k, b in STORE["boqs"].items() if k not in before][0]
    stored = new["line_items"][0]
    assert not any(k.startswith("_") for k in stored), sorted(stored)
    assert stored["description"] == "150mm dia     ISI"
    assert stored["supply_base_rate"] == 1760.0


# ═══ Bulk insert ═══════════════════════════════════════════════════════════

def test_insert_family_builds_a_header_and_one_child_per_size(seeded):
    res = _session(f"""
        STUB['bulk-spec'].value = '{_sid("PIPE-MS-C-1239-AG")}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        dump();
    """)
    assert len(res) == 10
    head, kids = res[0], res[1:]
    assert head["is_header"] is True and head["item_no"] == "1"
    assert len(head["description"]) > 1000
    assert [k["item_no"] for k in kids] == [
        "1.a", "1.b", "1.c", "1.d", "1.e", "1.f", "1.g", "1.h", "1.i"]
    assert all(k["parent_item_no"] == "1" for k in kids)
    assert kids[0]["supply_base_rate"] == ""      # "-" in the source
    assert kids[1]["supply_base_rate"] == "1760"
    assert kids[1]["install_base_rate"] == "1200"


def test_insert_family_rows_are_still_re_pickable(seeded):
    """A bulk-inserted row must behave like a hand-picked one — its values are
    auto, so changing its spec replaces them."""
    res = _session(f"""
        STUB['bulk-spec'].value = '{_sid("PIPE-MS-C-1239-AG")}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        openLine(1);
        fireSelect(1, 'spec', '{_sid(AXE)}');
        dumpLine(1);
    """)
    assert "firemans axe" in res["description"]
    assert res["unit"] == "Nos."
    assert res["supply_hsn"] == "84241000"


def test_insert_family_numbers_after_what_is_already_there(seeded):
    res = _session(f"""
        for (var n = 1; n <= 23; n++) {{
          var L = blankLine(); L.section = 'A'; L.item_no = String(n);
          MODEL.lines.push(L);
        }}
        renderLines();
        STUB['bulk-spec'].value = '{_sid("PIPE-MS-C-1239-AG")}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        console.log(JSON.stringify(MODEL.lines.slice(23).map(function (l) {{
          return l.item_no; }})));
    """)
    assert res == ["24", "24.a", "24.b", "24.c", "24.d", "24.e",
                   "24.f", "24.g", "24.h", "24.i"]


def test_insert_family_on_an_unsized_spec_makes_one_plain_line(seeded):
    res = _session(f"""
        STUB['bulk-spec'].value = '{_sid(AXE)}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        dump();
    """)
    assert len(res) == 1
    assert res[0]["is_header"] is False
    assert res[0]["parent_item_no"] == ""
    assert res[0]["unit"] == "Nos."
