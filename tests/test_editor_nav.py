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
        saveJSON();
        console.log(STUB['boq_json'].value);
    """, boot=_demo_boot(client))
    assert any(k.startswith("_") for k in posted["lines"][0]), \
        "the fixture should be posting UI state, or this proves nothing"

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
