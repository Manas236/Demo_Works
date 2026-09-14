"""
Navigating a 97-line schedule — collapse, expand, jump, and the summary row.

Driven through the RENDERED controls, the same way `test_picker_js.py` was
rebuilt: every toggle here is fired by pulling its `onclick` out of the
rendered HTML, so an unwired or missing control fails the test. Asserting that
a function exists in the source would prove nothing about whether it is
reachable.

The one-line summary is the deliverable; collapsing is how it becomes
readable. Most of these tests are about the summary being *right*, because a
summary that misreports a line is worse than no summary.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")

_DRIVER = """
function editorHtml() { return STUB['line-editor'].innerHTML; }

/* Fire a rendered control's onclick, the way a click would. */
function fireClick(re, what) {
  var m = re.exec(editorHtml());
  if (!m) throw new Error('no rendered control for ' + what);
  eval(m[1].replace(/&quot;/g, '"'));
}
function clickLine(i)    { fireClick(new RegExp('onclick="(toggleLine\\\\(' + i + '\\\\))"'), 'line ' + i); }
function clickSection(s) { fireClick(new RegExp('onclick="(toggleSection\\\\(' + s + '\\\\))"'), 'section ' + s); }

function jumpHtml() { return STUB['jump-bar'].innerHTML; }
function clickJump(s) {
  var m = new RegExp('onclick="(jumpTo\\\\(' + s + '\\\\))"').exec(jumpHtml());
  if (!m) throw new Error('no jump button for section ' + s);
  eval(m[1]);
}
function clickExpandAll()   { eval(/onclick="(expandAll\\(\\))"/.exec(jumpHtml())[1]); }
function clickCollapseAll() { eval(/onclick="(collapseAll\\(\\))"/.exec(jumpHtml())[1]); }

/* Which item numbers are actually visible as summary rows. */
function visibleItems() {
  var out = [], re = /<span class="ls-no">([^<]*)<\\/span>/g, m;
  while ((m = re.exec(editorHtml())) !== null) out.push(m[1]);
  return out;
}
/* Which lines have their edit panel open (a textarea only exists when open). */
function openPanels() {
  var out = [], re = /data-line="(\\d+)"[^]*?/g;
  var cards = editorHtml().split('<div class="line-card');
  for (var i = 1; i < cards.length; i++) {
    var d = /data-line="(\\d+)"/.exec(cards[i]);
    if (d && cards[i].indexOf('lc-body') !== -1) out.push(parseInt(d[1], 10));
  }
  return out;
}
function summaryOf(i) {
  var cards = editorHtml().split('<div class="line-card');
  for (var k = 1; k < cards.length; k++) {
    var d = /data-line="(\\d+)"/.exec(cards[k]);
    if (d && parseInt(d[1], 10) === i) {
      var out = {}, re = /<span class="(ls-[a-z]+)">([^<]*)<\\/span>/g, m;
      while ((m = re.exec(cards[k])) !== null) {
        if (!out[m[1]]) out[m[1]] = [];
        out[m[1]].push(m[2]);
      }
      return out;
    }
  }
  return null;
}
"""


_DOM = """
/* A `line-editor` that answers a query, so the code that marks a newly
   inserted row and scrolls to it runs here rather than being skipped. Nodes
   are minted from the rendered HTML on every call, because the editor replaces
   its innerHTML wholesale on every render and the real nodes go with it. */
var FLASHED = [], SCROLLED = [], FOCUSED = '';
function _stubNode(n) {
  return {
    offsetWidth: 0,
    getAttribute: function(k) { return k === 'data-line' ? n : null; },
    classList: {
      add: function(c) { FLASHED.push(n + ':' + c); },
      remove: function(c) {}
    },
    scrollIntoView: function(o) { SCROLLED.push([n, o.block]); }
  };
}
STUB['line-editor'].querySelectorAll = function(sel) {
  var out = [], re = /data-line="(\\d+)"/g, m;
  while ((m = re.exec(STUB['line-editor'].innerHTML)) !== null) {
    out.push(_stubNode(m[1]));
  }
  return out;
};
STUB['bulk-spec'].focus = function() { FOCUSED = 'bulk-spec'; };
"""


def _session(script: str, boot=None):
    import boq

    payload = boq._spec_catalog_json()
    harness = (
        "var BOQ_SPECS_JSON = " + payload + ";\n"
        "var STUB = { 'bulk-spec': {value:'', innerHTML:''}, "
        "'bulk-section': {value:'A', innerHTML:''}, "
        "'line-editor': {innerHTML:''}, 'sec-editor': {innerHTML:''}, "
        "'jump-bar': {innerHTML:''}, 'boq_json': {value:''} };\n"
        "var document = { body: {}, getElementById: function(id) "
        "{ return STUB[id] || null; } };\n"
        "var SCROLLS = [];\n"
        "var window = { scrollTo: function(x, y) { SCROLLS.push([x, y]); } };\n"
        + _DOM
    )
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = js.replace("BOQ_SPECS", "BOQ_SPECS_JSON")
    js = js.replace("BOQ_BOOT", json.dumps(boot or {
        "sections": [{"code": "A", "title": "Sprinklers", "areas": ["L0"]}],
        "lines": []}))
    js = js.replace("BOQ_ADDR", "{}")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf8") as fh:
        fh.write(harness + js + _DRIVER + "\n" + script)
        path = fh.name
    try:
        out = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=40, encoding="utf8")
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _demo_boot(client):
    """The real 97-line demo payload, exactly as the page ships it."""
    html = client.get("/boq/create?demo=1").get_data(as_text=True)
    return json.loads(re.search(r"var MODEL = (\{.*?\});\n", html, re.S).group(1))


@pytest.fixture()
def seeded(client):
    client.get("/boq/")
    return client


# ═══ Default state ════════════════════════════════════════════════════════

def test_a_loaded_boq_opens_fully_collapsed(seeded, client):
    res = _session("""
        console.log(JSON.stringify({
          openPanels: openPanels(),
          visible: visibleItems(),
          sectionBars: (editorHtml().match(/class="sec-bar"/g) || []).length
        }));
    """, boot=_demo_boot(client))
    assert res["openPanels"] == [], "97 panels open is the bug"
    assert res["visible"] == [], "sections start collapsed too"
    assert res["sectionBars"] == 3


def test_every_section_gets_a_bar_with_its_totals(seeded, client):
    res = _session("""
        var bars = editorHtml().split('class="sec-bar"');
        var out = [];
        for (var i = 1; i < bars.length; i++) {
          var code = /<span class="sb-code">([^<]*)</.exec(bars[i]);
          var rates = [], re = /<span class="ls-rate">([^<]*)</g, m;
          while ((m = re.exec(bars[i].split('</div>')[0])) !== null) rates.push(m[1]);
          out.push({code: code ? code[1] : null, rates: rates});
        }
        console.log(JSON.stringify(out));
    """, boot=_demo_boot(client))
    assert [b["code"] for b in res] == ["A", "B", "C"]
    # The section bar carries the section's own supply / installation totals.
    assert res[0]["rates"] == ["4,83,764.50", "3,11,350.00"]
    assert res[1]["rates"] == ["56,59,023.80", "23,57,400.00"]
    assert res[2]["rates"] == ["34,775.00", "3,45,000.00"]


# ═══ The summary row — the deliverable ════════════════════════════════════

def test_the_summary_carries_item_description_qty_and_both_rates(seeded, client):
    res = _session("""
        clickSection(0);
        var i = -1;
        for (var k = 0; k < MODEL.lines.length; k++) {
          if (MODEL.lines[k].item_no === '4') { MODEL.lines[k]._open = true; }
          if (MODEL.lines[k].item_no === '4.1') i = k;
        }
        renderLines();
        console.log(JSON.stringify({i: i, summary: summaryOf(i)}));
    """, boot=_demo_boot(client))
    s = res["summary"]
    assert s["ls-no"] == ["4.1"]
    # Runs of whitespace are collapsed: the stored description is
    # "150mm dia     ISI" and a one-line summary must not spend a third of its
    # width on the client's column padding.
    assert s["ls-desc"] == ["150mm dia ISI"]
    assert s["ls-qty"] == ["4 Mtrs."]
    assert s["ls-rate"] == ["2,024.00", "1,200.00"]


def test_a_long_description_is_truncated_not_wrapped(seeded, client):
    res = _session("""
        clickSection(0);
        var i = 0;
        for (var k = 0; k < MODEL.lines.length; k++) {
          if (MODEL.lines[k].item_no === '4' && MODEL.lines[k].is_header) i = k;
        }
        console.log(JSON.stringify({
          full: MODEL.lines[i].description.length,
          shown: summaryOf(i)['ls-desc'][0]
        }));
    """, boot=_demo_boot(client))
    assert res["full"] > 1000
    assert len(res["shown"]) <= 96
    assert res["shown"].endswith("…")
    assert "\n" not in res["shown"]


def test_a_header_summary_says_how_many_items_it_holds(seeded, client):
    res = _session("""
        clickSection(1);
        var i = 0;
        for (var k = 0; k < MODEL.lines.length; k++) {
          if (MODEL.lines[k].item_no === '24' && MODEL.lines[k].is_header) i = k;
        }
        console.log(JSON.stringify(summaryOf(i)));
    """, boot=_demo_boot(client))
    assert res["ls-tag"] == ["spec · 9 items"]
    assert "ls-rate" not in res, "a header has no rate to show"


# ═══ Folding ══════════════════════════════════════════════════════════════

def test_a_collapsed_header_takes_its_children_with_it(seeded, client):
    """Item 24 closed must hide 24.a-24.i."""
    res = _session("""
        clickSection(1);
        var before = visibleItems();
        var i = 0;
        for (var k = 0; k < MODEL.lines.length; k++) {
          if (MODEL.lines[k].item_no === '24' && MODEL.lines[k].is_header) i = k;
        }
        clickLine(i);                 /* open the family */
        var opened = visibleItems();
        clickLine(i);                 /* fold it again */
        var closed = visibleItems();
        console.log(JSON.stringify({before: before, opened: opened, closed: closed}));
    """, boot=_demo_boot(client))
    kids = ["24.a", "24.b", "24.c", "24.d", "24.e", "24.f", "24.g", "24.h", "24.i"]
    assert not any(k in res["before"] for k in kids)
    assert all(k in res["opened"] for k in kids)
    assert not any(k in res["closed"] for k in kids)
    assert "24" in res["closed"], "the header itself stays visible"


def test_folding_one_family_leaves_the_others_alone(seeded, client):
    res = _session("""
        clickSection(1);
        var a = 0, b = 0;
        for (var k = 0; k < MODEL.lines.length; k++) {
          if (MODEL.lines[k].is_header && MODEL.lines[k].item_no === '24') a = k;
          if (MODEL.lines[k].is_header && MODEL.lines[k].item_no === '26') b = k;
        }
        clickLine(a); clickLine(b);
        clickLine(a);
        console.log(JSON.stringify(visibleItems()));
    """, boot=_demo_boot(client))
    assert "24.a" not in res
    assert "26.a" in res


# ═══ Expand / collapse / jump ═════════════════════════════════════════════

def test_expand_all_then_collapse_all(seeded, client):
    res = _session("""
        clickExpandAll();
        var open = openPanels().length;
        var vis = visibleItems().length;
        clickCollapseAll();
        console.log(JSON.stringify({
          openAfterExpand: open, visibleAfterExpand: vis,
          openAfterCollapse: openPanels().length,
          visibleAfterCollapse: visibleItems().length
        }));
    """, boot=_demo_boot(client))
    assert res["openAfterExpand"] == 97
    assert res["visibleAfterExpand"] == 97
    assert res["openAfterCollapse"] == 0
    assert res["visibleAfterCollapse"] == 0


def test_jump_opens_the_section_it_jumps_to(seeded, client):
    res = _session("""
        clickJump(2);
        console.log(JSON.stringify({
          visible: visibleItems().length,
          sectionOpen: MODEL.sections.map(function (s) { return !!s._open; })
        }));
    """, boot=_demo_boot(client))
    assert res["sectionOpen"] == [False, False, True]
    assert res["visible"] > 0


def test_the_jump_bar_lists_every_section(seeded, client):
    res = _session("""
        console.log(JSON.stringify({
          buttons: (jumpHtml().match(/jumpTo\\(\\d+\\)/g) || []),
          hasExpand: jumpHtml().indexOf('expandAll()') !== -1,
          hasCollapse: jumpHtml().indexOf('collapseAll()') !== -1
        }));
    """, boot=_demo_boot(client))
    assert res["buttons"] == ["jumpTo(0)", "jumpTo(1)", "jumpTo(2)"]
    assert res["hasExpand"] and res["hasCollapse"]


# ═══ Newly added / edited lines stay open ═════════════════════════════════

def test_a_new_line_is_added_open_and_visible(seeded, client):
    res = _session("""
        clickCollapseAll();
        addLine();
        console.log(JSON.stringify({
          open: openPanels(),
          sectionOpened: !!MODEL.sections[0]._open,
          count: MODEL.lines.length
        }));
    """, boot=_demo_boot(client))
    assert res["open"] == [97], "the new line must be the open one"
    assert res["sectionOpened"], "adding into a collapsed section would hide it"


def test_editing_a_line_leaves_it_open(seeded, client):
    """A pick re-renders the editor; the row being worked on must not shut."""
    res = _session("""
        addLine();
        var i = MODEL.lines.length - 1;
        setLine(i, 'description', 'typed');
        renderLines();
        var afterType = openPanels();
        fillFromSpec(i, Object.keys(SPECS)[0]);
        console.log(JSON.stringify({afterType: afterType, afterPick: openPanels()}));
    """, boot=_demo_boot(client))
    assert res["afterType"] == [97]
    assert res["afterPick"] == [97]


def test_bulk_insert_shows_the_family_without_opening_ten_panels(seeded, client):
    import boq
    sid = [k for k, v in json.loads(boq._spec_catalog_json()).items()
           if v["code"] == "PIPE-MS-C-1239-AG"][0]
    res = _session(f"""
        STUB['bulk-spec'].value = '{sid}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        console.log(JSON.stringify({{
          visible: visibleItems(),
          openPanels: openPanels().length
        }}));
    """)
    assert res["visible"] == ["1", "1.a", "1.b", "1.c", "1.d", "1.e",
                              "1.f", "1.g", "1.h", "1.i"]
    assert res["openPanels"] == 1, "only the header opens; ten panels is the bug"


# ═══ State lives on the line, not on its position ════════════════════════

def test_open_state_follows_the_line_when_one_is_deleted(seeded, client):
    """
    The class the picker's PICK map fell into: anything keyed by row index
    desyncs the moment a row is removed.
    """
    res = _session("""
        addLine(); addLine(); addLine();
        var n = MODEL.lines.length;
        MODEL.lines[n-3]._open = false;
        MODEL.lines[n-2]._open = false;
        MODEL.lines[n-1]._open = true;
        MODEL.lines[n-1].item_no = 'KEEPME';
        renderLines();
        delLine(n - 3);
        var open = openPanels();
        console.log(JSON.stringify({
          openItemNos: open.map(function (i) { return MODEL.lines[i].item_no; })
        }));
    """, boot=_demo_boot(client))
    assert res["openItemNos"] == ["KEEPME"]


def test_orphan_lines_are_shown_not_hidden(seeded, client):
    """An invisible line still posts and still counts toward a total."""
    res = _session("""
        addLine();
        MODEL.lines[MODEL.lines.length - 1].section = 'GONE';
        MODEL.lines[MODEL.lines.length - 1].item_no = 'ORPH';
        renderLines();
        console.log(JSON.stringify({
          warned: editorHtml().indexOf('no longer exists') !== -1,
          visible: visibleItems().indexOf('ORPH') !== -1
        }));
    """, boot=_demo_boot(client))
    assert res["warned"] and res["visible"]


# ═══ Collapsed lines must still POST ══════════════════════════════════════

def test_saveJSON_includes_every_line_however_collapsed(seeded, client):
    res = _session("""
        clickCollapseAll();
        saveJSON();
        console.log(STUB['boq_json'].value);
    """, boot=_demo_boot(client))
    assert len(res["lines"]) == 97
    assert len(res["sections"]) == 3


def test_the_demo_round_trips_fully_collapsed(seeded, client):
    """
    THE constraint: a collapsed line is hidden, not excluded. Collapse
    everything, post it, and the schedule must still total to the paisa.
    """
    import boq
    from store import STORE

    posted = _session("""
        clickCollapseAll();
        saveJSON();
        console.log(STUB['boq_json'].value);
    """, boot=_demo_boot(client))

    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "Sify Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "rate_basis_label": "Mohali Rates",
        "boq_json": json.dumps(posted)})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]

    new = [b for k, b in STORE["boqs"].items() if k not in before][0]
    assert len(new["line_items"]) == 97
    sup, ins, _t = boq.boq_totals(new)
    assert round(sup, 2) == 6177563.30
    assert round(ins, 2) == 3013750.00


def test_no_ui_state_reaches_the_record(seeded, client):
    """
    The editor's bookkeeping is posted so a rejected form can restore it, and
    the SERVER is what keeps it out of the record — `_clean_lines` and
    `_clean_sections` build fresh dicts from named keys.
    """
    from store import STORE

    posted = _session("""
        clickExpandAll();
        fillFromSpec(0, Object.keys(SPECS)[0]);
        MODEL.lines[1]._more = true;       /* the fold, opened */
        saveJSON();
        console.log(STUB['boq_json'].value);
    """, boot=_demo_boot(client))
    assert any(k.startswith("_") for k in posted["lines"][0]), \
        "the fixture should be posting UI state, or this proves nothing"
    assert posted["lines"][1]["_more"] is True

    before = set(STORE["boqs"])
    client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "P", "account_name": "A",
        "boq_json": json.dumps(posted)})
    new = [b for k, b in STORE["boqs"].items() if k not in before][0]
    for li in new["line_items"]:
        assert not any(k.startswith("_") for k in li), sorted(li)
    for sec in new["sections"]:
        assert set(sec) == {"code", "title", "areas"}


# ═══ Rejected POSTs ═══════════════════════════════════════════════════════

def test_a_rejected_post_forces_the_offending_line_open(seeded, client):
    """
    Every line is collapsed by default. A complaint about line 47 that leaves
    line 47 shut is worse than no validation.
    """
    boot = _demo_boot(client)
    boot["lines"][46]["description"] = ""          # a real, findable failure
    for line in boot["lines"]:
        line["_open"] = False
    for sec in boot["sections"]:
        sec["_open"] = False

    r = client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "P", "account_name": "A",
        "boq_json": json.dumps(boot)})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "needs a description" in html

    model = json.loads(re.search(r"var MODEL = (\{.*?\});\n", html, re.S).group(1))
    assert model["lines"][46]["_open"] is True, "the failing line stayed shut"
    opened = [s for s in model["sections"] if s.get("_open")]
    assert opened and opened[0]["code"] == model["lines"][46]["section"]


def test_a_rejected_post_keeps_input_and_open_state(seeded, client):
    boot = _demo_boot(client)
    boot["lines"][0]["_open"] = True
    boot["lines"][3]["_open"] = True
    boot["sections"][1]["_open"] = True
    boot["lines"][5]["description"] = "A" * 1500

    r = client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "Kept Project",
        "account_name": "",                          # the rejection
        "boq_json": json.dumps(boot)})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Kept Project" in html
    model = json.loads(re.search(r"var MODEL = (\{.*?\});\n", html, re.S).group(1))
    assert model["lines"][0]["_open"] is True
    assert model["lines"][3]["_open"] is True
    assert model["sections"][1]["_open"] is True
    assert len(model["lines"][5]["description"]) == 1500


# ═══ Inserting a row does not throw the page away ════════════════════

def test_inserting_a_family_leaves_the_viewport_where_it_was(seeded, client):
    """
    The bulk bar sits ABOVE the list, and inserting a spec is something you do
    six times in a row. Ending the insert at the bottom of the document put the
    control being used off screen after every single click — so the page must
    not move at all, and the picker must still be the thing under the cursor.
    """
    import boq
    sid = [k for k, v in json.loads(boq._spec_catalog_json()).items()
           if v["code"] == "PIPE-MS-C-1239-AG"][0]
    res = _session(f"""
        STUB['bulk-spec'].value = '{sid}';
        insertFamily();
        console.log(JSON.stringify({{
          scrolls: SCROLLS, scrolledInto: SCROLLED,
          flashed: FLASHED, focused: FOCUSED
        }}));
    """)
    assert res["scrolls"] == [], "jumping to the bottom of the page is the bug"
    assert res["scrolledInto"] == [], "nor by any other name"
    assert res["focused"] == "bulk-spec", "the next insert starts here"
    assert res["flashed"] == [f"{n}:just-added" for n in range(10)], \
        "the whole family says where it landed, header and all ten rows"


def test_a_second_insert_marks_only_the_second_family(seeded, client):
    """The mark says what just happened, not what has ever happened."""
    import boq
    specs = json.loads(boq._spec_catalog_json())
    sid = [k for k, v in specs.items() if v["code"] == "PIPE-MS-C-1239-AG"][0]
    res = _session(f"""
        STUB['bulk-spec'].value = '{sid}';
        insertFamily();
        FLASHED = [];
        STUB['bulk-spec'].value = '{sid}';
        insertFamily();
        console.log(JSON.stringify({{flashed: FLASHED, scrolls: SCROLLS}}));
    """)
    assert res["scrolls"] == []
    assert res["flashed"] == [f"{n}:just-added" for n in range(10, 20)]


def test_adding_a_line_scrolls_no_further_than_the_new_row(seeded, client):
    """
    `+ Add line` is different: the row opens expanded and is there to be typed
    into, so the page does follow it — but only as far as `nearest`, which is a
    no-op for a row already on screen and never overshoots one that is not.
    """
    res = _session("""
        addLine();
        console.log(JSON.stringify({
          scrolls: SCROLLS, scrolledInto: SCROLLED, flashed: FLASHED
        }));
    """)
    assert res["scrolls"] == [], "the document end is not where the row is"
    assert res["scrolledInto"] == [["0", "nearest"]]
    assert res["flashed"] == ["0:just-added"]


# ═══ The open panel — four bands, then a fold ═════════════════════════════
#
# Twenty-two controls in one flat stack was the complaint. The panel now reads
# top-down in the order a line is made — where it sits and what it is, how
# much, the rates — and folds the tax codes and the internal remark away
# behind a summary line that still says what they are. These tests hold the
# order and the fold; the picker tests already drive the controls inside it.

_PANEL = """
function panelOf(i) {
  var cards = editorHtml().split('<div class="line-card');
  for (var k = 1; k < cards.length; k++) {
    var d = /data-line="([0-9]+)"/.exec(cards[k]);
    if (d && parseInt(d[1], 10) === i) return cards[k];
  }
  return '';
}
/* The index of a priced line, opened — together with the header it sits
   under, because a closed header folds its children away. */
function openLine(item) {
  var i = -1;
  for (var k = 0; k < MODEL.lines.length; k++) {
    if (MODEL.lines[k].item_no === item && !MODEL.lines[k].is_header) i = k;
  }
  var L = MODEL.lines[i];
  L._open = true;
  for (var h = 0; h < MODEL.lines.length; h++) {
    var H = MODEL.lines[h];
    if (H.is_header && H.section === L.section && H.item_no === L.parent_item_no) H._open = true;
  }
  renderLines();
  return i;
}
/* Where each band starts in the panel's HTML; -1 when it is not there. */
function bands(html) {
  return {
    ident: html.indexOf('class="lc-ident"'),
    desc:  html.indexOf('class="form-group lc-desc"'),
    qty:   html.indexOf('class="lc-areas"'),
    rates: html.indexOf('class="lc-rates"'),
    fold:  html.indexOf('<details class="lc-more"')
  };
}
"""


def test_an_open_line_reads_identity_description_quantity_rates_then_the_fold(seeded, client):
    res = _session(_PANEL + """
        clickSection(0);
        var i = openLine('4.1');
        var p = panelOf(i);
        var qtyBand = p.slice(p.indexOf('class="lc-areas"'), p.indexOf('class="lc-rates"'));
        var fold = p.slice(p.indexOf('<details class="lc-more"'));
        console.log(JSON.stringify({
          i: i, bands: bands(p),
          foldClosed: p.indexOf('<details class="lc-more" ontoggle') !== -1
                   && p.indexOf('<details class="lc-more" open') === -1,
          summary: (/class="lc-more-sum"[^>]*>([^<]*)</.exec(p) || [])[1],
          unitInQtyBand: qtyBand.indexOf('>Unit<') !== -1,
          rateRows: (p.match(/class="lc-rl"/g) || []).length,
          rateCells: (p.match(/class="lc-rc"/g) || []).length,
          hintBoxes: [p.indexOf('id="sd' + i + '"') !== -1, p.indexOf('id="id' + i + '"') !== -1],
          taxOnlyBehindTheFold: (p.match(/supply_hsn/g) || []).length === 1
                             && fold.indexOf('supply_hsn') !== -1
                             && fold.indexOf('install_sac') !== -1
                             && fold.indexOf('&quot;remark&quot;') !== -1,
          headHasToggleAndRemove: /class="lc-head"[^]*?id="hdr[^]*?delLine[(]/.test(
                                    p.slice(0, p.indexOf('class="lc-ident"')))
        }));
    """, boot=_demo_boot(client))
    b = res["bands"]
    assert -1 not in b.values(), b
    assert b["ident"] < b["desc"] < b["qty"] < b["rates"] < b["fold"], b
    assert res["foldClosed"], "the fold opens only when asked"
    # Closed, it still says what it holds — nothing is hidden, only tucked away.
    assert res["summary"] == "HSN 73063090 @ 18% &nbsp;&middot;&nbsp; SAC 995462 @ 18%"
    assert res["unitInQtyBand"], '"4 Mtrs." is one fact, so Unit sits with the quantity'
    assert res["rateRows"] == 2 and res["rateCells"] == 6, "two legs down, three figures across"
    assert res["hintBoxes"] == [True, True], "hint() still has somewhere to write"
    assert res["taxOnlyBehindTheFold"]
    assert res["headHasToggleAndRemove"]


def test_the_fold_remembers_it_was_opened_across_a_re_render(seeded, client):
    """
    `_more` lives on the line like `_open`, so changing the spec — which
    re-renders — does not slam the fold shut under the user.
    """
    res = _session(_PANEL + """
        clickSection(0);
        var i = openLine('4.1');
        MODEL.lines[i]._more = true;            /* what ontoggle does */
        fillFromSpec(i, Object.keys(SPECS)[0]); /* a re-render */
        console.log(JSON.stringify({
          open: panelOf(i).indexOf('<details class="lc-more" open') !== -1,
          posted: (saveJSON(), JSON.parse(STUB['boq_json'].value).lines[i]._more)
        }));
    """, boot=_demo_boot(client))
    assert res["open"]
    assert res["posted"] is True, "posted, so a rejected form can restore it"


def test_typing_behind_the_fold_keeps_its_summary_line_current(seeded, client):
    """
    Typing does not re-render (it would take the caret), so the summary the
    fold shows when closed is patched in place — a remark typed and folded
    away is still on the face of the row.
    """
    res = _session(_PANEL + """
        clickSection(0);
        var i = openLine('4.1');
        STUB['ms' + i] = {innerHTML: 'stale'};
        setLine(i, 'remark', 'tamper switch extra');
        var a = STUB['ms' + i].innerHTML;
        setLine(i, 'supply_hsn', '');
        var b = STUB['ms' + i].innerHTML;
        setLine(i, 'supply_gst_rate', ''); setLine(i, 'install_sac', '');
        setLine(i, 'install_gst_rate', ''); setLine(i, 'remark', '');
        console.log(JSON.stringify({a: a, b: b, c: STUB['ms' + i].innerHTML}));
    """, boot=_demo_boot(client))
    assert res["a"].endswith("&#8220;tamper switch extra&#8221;")
    assert res["a"].startswith("HSN 73063090 @ 18%")
    assert res["b"].startswith("supply @ 18%"), "a rate with no code still reads"
    assert res["c"] == "none set"


def test_a_header_row_shows_identity_description_and_remark_and_nothing_else(seeded, client):
    """
    A header carries the clause and no quantity or rate, and the server zeroes
    its tax codes — so its panel has no quantity band, no rate table and no
    fold. Its row type shows ticked on the panel's head.
    """
    res = _session(_PANEL + """
        clickSection(0);
        var i = -1;
        for (var k = 0; k < MODEL.lines.length; k++) {
          if (MODEL.lines[k].item_no === '4' && MODEL.lines[k].is_header) i = k;
        }
        MODEL.lines[i]._open = true;
        renderLines();
        var p = panelOf(i);
        console.log(JSON.stringify({
          bands: bands(p),
          ticked: p.indexOf('id="hdr' + i + '" checked') !== -1,
          remark: p.indexOf('&quot;remark&quot;') !== -1
        }));
    """, boot=_demo_boot(client))
    b = res["bands"]
    assert b["ident"] != -1 and b["desc"] != -1
    assert b["qty"] == -1 and b["rates"] == -1 and b["fold"] == -1, b
    assert res["ticked"] and res["remark"]


# ═══ A new line is quantified at 1 ════════════════════════════════════════
#
# A line inserted into a section that takes a typed total arrives at 1 rather
# than blank: a schedule line is one of something until site measurement says
# otherwise, and a row born at 0 trips the zero-quantity band on every insert.
# It is a TYPED total, so a section with an area breakdown — where the total
# is derived from the area boxes and which floor a "1" belongs on is not the
# editor's to guess — starts blank as before. These tests hold both halves,
# the bulk insert, the section move, and the server's precedence for a
# figure carried into an area section.

_QTY = """
STUB['zeroqty-hint'] = {innerHTML: ''};
function panelOf(i) {
  var cards = editorHtml().split('<div class="line-card');
  for (var k = 1; k < cards.length; k++) {
    var d = /data-line="([0-9]+)"/.exec(cards[k]);
    if (d && parseInt(d[1], 10) === i) return cards[k];
  }
  return '';
}
/* The Total Qty control as rendered: a typed box's value, a derived total's
   read-only text, or null when the row shows no quantity band at all. */
function renderedTotal(i) {
  var p = panelOf(i);
  var typed = /<label>Total Qty<\\/label>\\s*<input type="text" value="([^"]*)"/.exec(p);
  if (typed) return {typed: typed[1]};
  var derived = /<label>Total Qty<\\/label>\\s*<div class="readonly-field"[^>]*>([^<]*)</.exec(p);
  if (derived) return {derived: derived[1]};
  return null;
}
function barRates(code) {
  var bars = editorHtml().split('class="sec-bar"');
  for (var i = 1; i < bars.length; i++) {
    var c = /<span class="sb-code">([^<]*)</.exec(bars[i]);
    if (!c || c[1] !== code) continue;
    var rates = [], re = /<span class="ls-rate">([^<]*)</g, m;
    while ((m = re.exec(bars[i].split('</div>')[0])) !== null) rates.push(m[1]);
    return rates;
  }
  return null;
}
function zeroBand() { return STUB['zeroqty-hint'].innerHTML; }
/* The summary's quantity, without the unit it is printed beside. */
function summaryQty(i) {
  var s = summaryOf(i);
  return s ? s['ls-qty'][0].trim() : null;
}
"""

_NO_AREAS = {"sections": [{"code": "C", "title": "Fire fighting", "areas": []}],
             "lines": []}
_MIXED = {"sections": [{"code": "C", "title": "Fire fighting", "areas": []},
                       {"code": "A", "title": "Sprinklers", "areas": ["L0"]}],
          "lines": []}


def test_a_new_line_in_a_section_without_areas_starts_at_one(seeded, client):
    res = _session(_QTY + """
        addLine();
        console.log(JSON.stringify({
          model: MODEL.lines[0].total_qty,
          rendered: renderedTotal(0),
          summaryQty: summaryQty(0),
          zeroBand: zeroBand()
        }));
    """, boot=_NO_AREAS)
    assert res["model"] == "1"
    assert res["rendered"] == {"typed": "1"}, "the Total Qty box must show the 1"
    assert res["summaryQty"] == "1"
    assert res["zeroBand"] == "", "a line born at 1 is not a line at 0"


def test_a_new_line_in_a_section_with_areas_starts_blank(seeded, client):
    """
    With an area breakdown the total IS the breakdown. A "1" would have to be
    put on some floor, and which one is not the editor's to decide.
    """
    res = _session(_QTY + """
        addLine();
        console.log(JSON.stringify({
          model: MODEL.lines[0].total_qty,
          areas: MODEL.lines[0].area_qty,
          rendered: renderedTotal(0),
          summaryQty: summaryQty(0)
        }));
    """)
    assert res["model"] == ""
    assert res["areas"] == {}
    assert res["rendered"] == {"derived": ""}
    assert res["summaryQty"] == ""


def test_a_family_inserted_into_a_no_area_section_lands_at_one_per_child(seeded, client):
    import boq
    cat = json.loads(boq._spec_catalog_json())
    sized = [k for k, v in cat.items() if v["code"] == "PIPE-MS-C-1239-AG"][0]
    unsized = [k for k, v in cat.items() if v["code"] == "HYD-FIREMANS-AXE"][0]
    res = _session(_QTY + f"""
        STUB['bulk-spec'].value = '{sized}';
        STUB['bulk-section'].value = 'C';
        insertFamily();
        STUB['bulk-spec'].value = '{unsized}';
        STUB['bulk-section'].value = 'C';
        insertFamily();
        console.log(JSON.stringify(MODEL.lines.map(function (L) {{
          return {{item: L.item_no, header: L.is_header, qty: L.total_qty}};
        }})));
    """, boot=_NO_AREAS)
    children = [r for r in res if not r["header"]]
    assert len(children) == 10, [r["item"] for r in res]
    assert all(r["qty"] == "1" for r in children), children
    assert [r["item"] for r in res][-1] == "2", "the unsized spec is one plain line"


def test_the_default_is_a_typed_total_and_posts_as_one(seeded, client):
    """The 1 is real: it rides in boq_json and the server prices the line at it."""
    import boq
    from store import STORE

    sid = [k for k, v in json.loads(boq._spec_catalog_json()).items()
           if v["code"] == "HYD-FIREMANS-AXE"][0]
    posted = _session(_QTY + f"""
        addLine();
        setLine(0, 'item_no', '1');
        fillFromSpec(0, '{sid}');
        setLine(0, 'supply_rate', '640');
        saveJSON();
        console.log(STUB['boq_json'].value);
    """, boot=_NO_AREAS)
    assert posted["lines"][0]["total_qty"] == "1"

    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={
        "date": "2026-06-15", "project_name": "P", "account_name": "A",
        "boq_json": json.dumps(posted)})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    new = [b for k, b in STORE["boqs"].items() if k not in before][0]
    line = new["line_items"][0]
    assert line["total_qty"] == 1.0
    assert line["supply_amount"] == 640.0


def test_moving_a_line_into_a_no_area_section_takes_the_default_when_blank(seeded, client):
    """
    Arriving in a section that takes a typed total with nothing typed is the
    same state as a fresh insert. A typed figure is never touched by a move.
    """
    res = _session(_QTY + """
        addLine();                      /* lands in A, which has areas: blank */
        var born = MODEL.lines[0].total_qty;
        setSection(0, 'C');
        var moved = MODEL.lines[0].total_qty;
        setLine(0, 'total_qty', '7');
        setSection(0, 'A');
        setSection(0, 'C');
        expandAll();
        console.log(JSON.stringify({
          born: born, moved: moved, typedSurvives: MODEL.lines[0].total_qty,
          rendered: renderedTotal(0)
        }));
    """, boot={"sections": [{"code": "A", "title": "", "areas": ["L0"]},
                            {"code": "C", "title": "", "areas": []}],
               "lines": []})
    assert res["born"] == ""
    assert res["moved"] == "1"
    assert res["typedSurvives"] == "7"
    assert res["rendered"] == {"typed": "7"}


def test_a_typed_total_does_not_count_once_the_line_is_in_an_area_section(seeded, client):
    """
    The server derives the total from the area boxes whenever the section
    declares any, whatever `total_qty` holds. The editor's section bar, the
    summary and the zero-quantity band must say the same — a default of 1
    carried into an area section would otherwise be priced on the bar and
    stored as 0.
    """
    res = _session(_QTY + """
        addLine();                      /* lands in C, no areas: 1 */
        setLine(0, 'item_no', '1');
        setLine(0, 'supply_rate', '500');
        renderLines();                  /* a value edit does not re-render */
        var beforeMove = {bar: barRates('C'), summary: summaryQty(0)};
        setSection(0, 'A');
        expandAll();
        var afterMove = {bar: barRates('A'), summary: summaryQty(0),
                         carried: MODEL.lines[0].total_qty,
                         zeroBand: zeroBand().indexOf('quantity of 0') !== -1};
        setArea(0, 'L0', '3');
        renderLines();
        console.log(JSON.stringify({
          beforeMove: beforeMove, afterMove: afterMove,
          afterArea: {bar: barRates('A'), summary: summaryQty(0)}
        }));
    """, boot=_MIXED)
    assert res["beforeMove"] == {"bar": ["500.00", ""], "summary": "1"}
    # Carried, but not counted: the breakdown is the total in section A, and
    # the bar prints nothing for a zero.
    assert res["afterMove"]["carried"] == "1"
    assert res["afterMove"]["bar"] == ["", ""]
    assert res["afterMove"]["summary"] == ""
    assert res["afterMove"]["zeroBand"], "a line with no floor filled in is at 0"
    assert res["afterArea"] == {"bar": ["1,500.00", ""], "summary": "3"}
