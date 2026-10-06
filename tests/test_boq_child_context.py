"""
Where a child line belongs, and what a real client sheet needs from the form
(30 September 2026 — the G4 follow-up, CLIENT_CHANGES.md §0, thirty-eighth
block).

Testing the guided BOQ import on the client's Jamnagar sheet showed four
things, and this file holds the answer to each. Every fixture here is
SYNTHETIC; the client's sheet is never read by a test.

A. **The parent rule.** The parent of a line is the line in the SAME SECTION
   whose item_no equals its parent_item_no; on a repeated number, the nearest
   one ABOVE the child (none above: the nearest below); none at all is a soft
   amber strip. `boq.parent_index()` on the server and `parentIndexAll()` in
   the editor are the same rule, and every child card carries its parent — a
   strip above Description, the collapsed header, the sticky bar, the flag
   banner — updated live.
B. **Every resolver of parent_item_no follows it**, and a BOQ whose sections
   A and C both carry an item 3 attaches each child to its own section's 3 on
   every reader: the pickers' fold, the documents raised from a schedule, the
   RA print's header row, the editor and the importer.
C. **"Not priced" is an answer.** Any typed number, 0 included, answers a
   rate flag; only a blank still asks. A "Not priced (₹0)" button types the 0,
   the line carries a grey chip, the bar says "All answered · N not priced";
   such a BOQ saves, and /boq/view names the lines in an amber note.
   ⚠ **Superseded 6 October 2026** (CLIENT_CHANGES.md §0, forty-fifth block,
   A3): a blank rate is itself a valid answer, so there is no flag, no button,
   no chip and no bar; the BOQ saves the blank as blank and /boq/view's note is
   a quiet "N lines have no rate, M lines have no quantity". The tests of C and
   D below are AMENDED to that rule, each declared, the old test kept above it.
D. **Units the sheet did not give** are a soft outline and a separate note
   in the bar — never counted among the fields that need you — and "Unit for
   all N sizes" fills only the blank ones. (⚠ From 6 October 2026: no outline
   and no note — A3. "Unit for all N sizes" stays.)
E. **An imported line's blank boxes say what goes in them in words.**
"""

import copy
import html as H
import io
import json
import re
import shutil
import subprocess

import pytest

import boq as BQ
import boqimport
import boqpick
import ra
from store import STORE
from test_ra_record import boq_line, claim, make_bill, make_boq

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def text(h: str) -> str:
    """Markup to the words a reader sees."""
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", h or "")).split())


def lid(n: int) -> str:
    """A well-formed line id — `boq._LINE_ID_RE` is 12 lower-case hex."""
    return f"{n:012x}"


def trunc(s: str, n: int) -> str:
    """`_BOQ_JS`'s `trunc()`, for the expected strings: whitespace collapsed,
    and past `n` the first n-1 characters and an ellipsis."""
    s = " ".join(str(s or "").split())
    return s[:n - 1] + "…" if len(s) > n else s


# ═══ Synthetic editor models — the shape the form posts ═════════════════════

def line(sec, ino, desc, parent="", header=False, **kw):
    d = {"line_id": "", "item_no": ino, "parent_item_no": parent, "section": sec,
         "is_header": header, "description": desc, "remark": "", "unit": "",
         "area_qty": {}, "total_qty": "" if header else "1",
         "supply_base_rate": "", "supply_escalation_pct": "", "supply_rate": "",
         "supply_hsn": "", "supply_gst_rate": "",
         "install_base_rate": "", "install_escalation_pct": "", "install_rate": "",
         "install_sac": "", "install_gst_rate": ""}
    d.update(kw)
    return d


CLAUSE_A = "Wet riser pipe, heavy class, ERW to IS 1239"
CLAUSE_C = ("Clean Agent (HFC-236) type modular fire extinguisher, wall mounted, "
            "complete with bracket, pressure gauge and discharge hose")


def need(row, f="rate"):
    m = f"Row {row}: a quantity but no rate on either track — type a rate"
    return {"_row": row, "_need": [{"f": f, "m": m}], "_flags": [m]}


def two_sections() -> dict:
    """Sections A and C BOTH carry an item 3 with children — the Jamnagar
    shape. C 3.a / 3.b are imported lines asking for a rate; A 3.b is a
    hand-typed line with a quantity and no rate; C 9.a names a parent its
    section does not have."""
    return {"sections": [{"code": "A", "title": "Hydrant", "areas": []},
                         {"code": "C", "title": "Extinguishers", "areas": []}],
            "lines": [
                line("A", "1", "Hydrant valve", total_qty="2", supply_rate="100", unit="Nos"),  # 0
                line("A", "3", CLAUSE_A, header=True, remark="Make: Jindal"),                  # 1
                line("A", "3.a", "150 mm", "3", total_qty="10", supply_rate="500",
                     unit="Mtrs"),                                                              # 2
                line("A", "3.b", "100 mm", "3", total_qty="5"),                                # 3
                line("C", "3", CLAUSE_C, header=True, remark="Make: KANEX", _row=69),          # 4
                line("C", "3.a", "2Kg", "3", total_qty="350", **need(70)),                     # 5
                line("C", "3.b", "4Kg", "3", total_qty="20", unit="Nos", **need(71)),          # 6
                line("C", "9.a", "Orphan", "9", total_qty="1", supply_rate="10", _row=72),     # 7
            ]}


def dups() -> dict:
    """Repeated numbers inside one section, a child above its parent, stray
    spaces, a self-reference, a cross-section miss and a priced parent."""
    return {"sections": [{"code": "B", "title": "", "areas": []},
                         {"code": "D", "title": "", "areas": []}],
            "lines": [
                line("B", "5", "First five", header=True),        # 0
                line("B", "5.a", "x", "5"),                       # 1 -> 0
                line("B", "5", "Second five", header=True),       # 2
                line("B", "5.a", "y", "5"),                       # 3 -> 2
                line("B", "7.a", "early", "7"),                   # 4 -> 5 (nearest BELOW)
                line("B", "7", "Seven", header=True),             # 5
                line("B", "8.a", "spaced", " 8 "),                # 6 -> 7
                line("B", "8", "Eight", header=True),             # 7
                line("D", "5.a", "other section", "5"),           # 8 -> -1 (no 5 in D)
                line("B", "9", "self", "9"),                      # 9 -> -1 (only itself)
                line("B", "10", "plain"),                         # 10 -> None
                line("B", "11", "priced parent", supply_rate="5"),  # 11
                line("B", "11.a", "kid", "11"),                   # 12 -> 11
            ]}


DUPS_PARENTS = [None, 0, None, 2, 5, None, 7, None, -1, -1, None, None, 11]


# ═══ The editor under Node ══════════════════════════════════════════════════
#
# A DOM that answers `getElementById` for any id the editor has rendered, so
# the live patches (`refreshCtx()`, `refreshNeeds()`) land somewhere readable
# rather than being skipped. Nodes are minted from the rendered HTML and
# dropped on every re-render, because the editor replaces its innerHTML
# wholesale and the real nodes go with it.

_DOM = r"""
var FOCUSED = null, SCROLLED = null, NODES = {}, LF = {};
function Elem(id) {
  this.id = id; this.value = ''; this.innerHTML = ''; this.className = '';
  this.style = {}; this.attrs = {}; this.cls = {};
  var self = this;
  this.classList = { add: function (c) { self.cls[c] = 1; },
                     remove: function (c) { delete self.cls[c]; },
                     contains: function (c) { return !!self.cls[c]; } };
  this.parentNode = { classList: { add: function () {}, remove: function () {} } };
}
Elem.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
Elem.prototype.getAttribute = function (k) { return this.attrs[k]; };
Elem.prototype.removeAttribute = function (k) { delete this.attrs[k]; };
Elem.prototype.scrollIntoView = function (o) { SCROLLED = this.id + ':' + o.block; };
Elem.prototype.focus = function () { FOCUSED = this.id; };
var STUB = {};
['bulk-spec','bulk-section','line-editor','sec-editor','boq_json','import-block',
 'dup-warn','zeroqty-hint','jump-bar','needs-bar'].forEach(function (k) { STUB[k] = new Elem(k); });
function onPage(attr) { return STUB['line-editor'].innerHTML.indexOf(attr) >= 0; }
var document = {
  getElementById: function (id) {
    if (STUB[id]) return STUB[id];
    if (!onPage('id="' + id + '"')) return null;
    return NODES[id] || (NODES[id] = new Elem(id));
  },
  querySelectorAll: function () { return []; },
  querySelector: function (sel) {
    var m = /data-lf="([^"]+)"/.exec(sel);
    if (!m || !onPage('data-lf="' + m[1] + '"')) return null;
    return LF[m[1]] || (LF[m[1]] = new Elem(m[1]));
  }
};
"""

_AFTER = r"""
renderLines = (function (orig) {
  return function () { NODES = {}; LF = {}; return orig.apply(this, arguments); };
})(renderLines);
function editorHtml() { return STUB['line-editor'].innerHTML; }
function cardOf(i) {
  var cards = editorHtml().split('<div class="line-card');
  for (var k = 1; k < cards.length; k++) {
    var d = /data-line="([0-9]+)"/.exec(cards[k]);
    if (d && parseInt(d[1], 10) === i) return cards[k];
  }
  return '';
}
function openAll() {
  for (var s = 0; s < MODEL.sections.length; s++) MODEL.sections[s]._open = true;
  for (var i = 0; i < MODEL.lines.length; i++) MODEL.lines[i]._open = true;
  renderLines();
}
function fire(re) {
  var m = re.exec(editorHtml());
  if (!m) throw new Error('no rendered control matching ' + re);
  eval(m[1].replace(/&quot;/g, '"'));
}
function out(x) { console.log(JSON.stringify(x)); }
"""


def _node(boot: dict, script: str, guide=None):
    js = BQ._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = (js.replace("BOQ_BOOT", json.dumps(boot))
            .replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}"))
    pre = _DOM + ("var BOQ_GUIDE = " + json.dumps(guide) + ";\n" if guide else "")
    res = subprocess.run([NODE], input=pre + js + "\n" + _AFTER + "\n" + script,
                         capture_output=True, text=True, timeout=40, encoding="utf8")
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


# ═══ A1. The parent rule ════════════════════════════════════════════════════

def test_the_parent_rule_on_the_server():
    """Same section; nearest above on a repeated number; nearest below when
    none is above; -1 when the section has no such number."""
    assert BQ.parent_index(two_sections()["lines"]) == [None, None, 1, 1, None, 4, 4, -1]
    assert BQ.parent_index(dups()["lines"]) == DUPS_PARENTS


def test_a_child_never_resolves_across_sections():
    lines = two_sections()["lines"]
    par = BQ.parent_index(lines)
    for i, p in enumerate(par):
        if p is not None and p >= 0:
            assert lines[p]["section"] == lines[i]["section"], (i, p)


def test_header_of_keeps_only_specification_families():
    """A priced parent is still a parent (the strip names it) but folds
    nothing: `header_of()` is what the fold and the print read."""
    lines = dups()["lines"]
    heads = BQ.header_of(lines)
    assert heads == {1: 0, 3: 2, 4: 5, 6: 7}
    assert 12 not in heads, "11.a's parent is a priced line — no family to fold into"


@needs_node
def test_python_and_js_agree_on_the_parent_rule():
    for model in (two_sections(), dups()):
        got = _node(model, "out(parentIndexAll());")
        assert got == BQ.parent_index(model["lines"]), model["lines"][0]["section"]


@needs_node
def test_the_fold_and_the_family_count_follow_the_rule():
    """A repeated header number folds only ITS OWN children — the editor's
    fold used to take every same-numbered child under both headers."""
    got = _node(dups(), """
      out({first: childrenOf(0), second: childrenOf(2), seven: childrenOf(5),
           priced: childrenOf(11), pricedKids: kidsOf(11)});
    """)
    assert got == {"first": [1], "second": [3], "seven": [4], "priced": [], "pricedKids": [12]}


# ═══ A2–A6. The context on every child card ═════════════════════════════════

def _strip(card: str, i: int) -> str:
    m = re.search(rf'<div class="([^"]*)" id="ctx{i}">(.*?)</div>', card, re.S)
    return (m.group(1), text(m.group(2))) if m else (None, None)


@needs_node
def test_every_child_card_carries_its_parent_above_the_description():
    got = _node(two_sections(), "openAll(); out({c: cardOf(5), a: cardOf(2), orphan: cardOf(7),"
                                " head: cardOf(4)});")
    cls, words = _strip(got["c"], 5)
    assert words == ("Part of C·3: " + CLAUSE_C + " · Make KANEX")
    assert "is-miss" not in cls and "is-none" not in cls
    # …and each resolves within its OWN section: A 3.a is A's pipe, not C's agent.
    assert _strip(got["a"], 2)[1] == "Part of A·3: " + CLAUSE_A + " · Make Jindal"
    # The strip sits ABOVE the description.
    c = got["c"]
    assert c.index('id="ctx5"') < c.index('class="form-group lc-desc')
    # A parent the section does not have: soft amber, never a block.
    ocls, owords = _strip(got["orphan"], 7)
    assert owords == "⚠ Under item 9: no such item in section C"
    assert "is-miss" in ocls
    # A line that is nobody's child draws the strip empty and hidden.
    assert _strip(got["head"], 4) == ("lc-ctx is-none", "")


@needs_node
def test_the_strip_is_clamped_and_a_click_opens_it():
    got = _node(two_sections(), """
      openAll();
      var before = cardOf(5);
      fire(/onclick="(toggleCtx\\(5\\))"/);
      out({before: before, node: document.getElementById('ctx5').className,
           flag: MODEL.lines[5]._ctx, after: (renderLines(), cardOf(5))});
    """)
    assert '<div class="lc-ctx" id="ctx5">' in got["before"]
    assert got["node"] == "lc-ctx is-open" and got["flag"] is True
    assert '<div class="lc-ctx is-open" id="ctx5">' in got["after"], "kept across a re-render"


@needs_node
def test_the_context_follows_the_typing_without_a_re_render():
    """The parent's description, its Make, this line's Under item and its
    Section — each updates the strip (and the collapsed header) live."""
    got = _node(two_sections(), """
      openAll();
      var html0 = editorHtml();
      setLine(4, 'description', 'Clean Agent NEW WORDING');
      var desc = [document.getElementById('ctx5').innerHTML,
                  document.getElementById('lsc5').innerHTML];
      setLine(4, 'remark', 'Make: CEASEFIRE');
      var make = document.getElementById('ctx5').innerHTML;
      setLine(5, 'parent_item_no', '9');
      var miss = [document.getElementById('ctx5').innerHTML,
                  document.getElementById('ctx5').className,
                  document.getElementById('lsc5').innerHTML];
      setLine(5, 'parent_item_no', '3');
      var back = document.getElementById('ctx5').innerHTML;
      var rerendered = editorHtml() !== html0;
      setSection(5, 'A');
      out({desc: desc, make: make, miss: miss, back: back, rerendered: rerendered,
           moved: cardOf(5)});
    """)
    assert "Clean Agent NEW WORDING" in text(got["desc"][0])
    assert text(got["desc"][1]) == "Clean Agent NEW WORDING ›"
    assert text(got["make"]).endswith("· Make CEASEFIRE")
    assert text(got["miss"][0]) == "⚠ Under item 9: no such item in section C"
    assert "is-miss" in got["miss"][1]
    assert text(got["miss"][2]) == "under 9 — not in C ›"
    assert text(got["back"]).startswith("Part of C·3: Clean Agent NEW WORDING")
    assert got["rerendered"] is False, "typing must not re-render — it would take the caret"
    # Moved to section A, the same "under 3" is A's item 3.
    assert _strip(got["moved"], 5)[1] == "Part of A·3: " + CLAUSE_A + " · Make Jindal"


@needs_node
def test_the_collapsed_header_reads_parent_then_own_description():
    got = _node(two_sections(), """
      for (var s = 0; s < MODEL.sections.length; s++) MODEL.sections[s]._open = true;
      MODEL.lines[4]._open = true; MODEL.lines[1]._open = true; renderLines();
      out({c: cardOf(5), a: cardOf(2), orphan: cardOf(7), head: cardOf(4)});
    """)

    def row(card):
        """(item no, context, own description) — the three spans, as read."""
        no = re.search(r'<span class="ls-no">(.*?)</span><span class="ls-ctx', card, re.S)
        ctx = re.search(r'<span class="ls-ctx[^"]*" id="lsc\d+">(.*?)</span>', card, re.S)
        desc = re.search(r'<span class="ls-desc">(.*)</span><span class="ls-(?:qty|tag)">',
                         card, re.S)
        return text(no.group(1)), text(ctx.group(1)), text(desc.group(1))

    assert row(got["c"])[:2] == ("3.a", trunc(CLAUSE_C, 40) + " ›")
    assert row(got["c"])[2].endswith("2Kg")
    assert row(got["a"]) == ("3.a", trunc(CLAUSE_A, 40) + " ›", "150 mm")
    assert row(got["orphan"])[1] == "under 9 — not in C ›"
    # The description span is still the line's OWN description, untouched.
    assert '<span class="ls-desc">150 mm</span>' in got["a"]
    assert '<span class="ls-ctx" id="lsc4"></span>' in got["head"], "not a child: empty"


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3
#   removes the "N fields need you" sticky bar and its Prev / Next: a blank is
#   a valid answer, so there is nothing to count.
#   The test as it stood:
#   @needs_node
#   def test_the_sticky_bar_names_where_you_are():
#       got = _node(two_sections(), """
#         var first = STUB['needs-bar'].innerHTML;
#         goNeed(1); var second = STUB['needs-bar'].innerHTML;
#         out({first: first, second: second});
#       """, guide={"imported": True})
#       parent = trunc(CLAUSE_C, 28)
#       assert f"2 fields need you 1 of 2 · C 3.a {parent} › 2Kg · rate" in text(got["first"])
#       assert f"2 of 2 · C 3.b {parent} › 4Kg · rate" in text(got["second"])

@needs_node
def test_the_sticky_bar_names_where_you_are():
    """There is no sticky bar any more (A3): an import's `_need` is ignored and
    nothing is counted, named or navigated."""
    got = _node(two_sections(), """
      out({bar: STUB['needs-bar'].innerHTML, n: needList().length,
           goNeed: typeof goNeed, renderNeedsBar: typeof renderNeedsBar});
    """, guide={"imported": True})
    assert got == {"bar": "", "n": 0, "goNeed": "undefined", "renderNeedsBar": "undefined"}


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3
#   removes the jump to the first field on load and the Prev / Next it rode on.
#   The test as it stood:
#   @needs_node
#   def test_next_after_answering_a_field_goes_on_to_the_one_after_it():
#       """Next counts from the field the user is on. It used to count a position
#       in a list that shrinks as fields are answered, and skipped one."""
#       model = two_sections()
#       model["lines"].append(line("C", "3.c", "6Kg", "3", total_qty="4", **need(73)))   # 8
#       got = _node(model, """
#         var first = CUR.i;
#         setLine(5, 'supply_rate', '120');
#         goNeed(1); var second = CUR.i;
#         goNeed(-1); var back = CUR.i;
#         out({first: first, second: second, back: back});
#       """, guide={"imported": True})
#       assert got == {"first": 5, "second": 6, "back": 8}

@needs_node
def test_next_after_answering_a_field_goes_on_to_the_one_after_it():
    """An import no longer takes the user to the first blank on load (A3)."""
    model = two_sections()
    model["lines"].append(line("C", "3.c", "6Kg", "3", total_qty="4", **need(73)))   # 8
    got = _node(model, "out({focused: FOCUSED, scrolled: SCROLLED});",
                guide={"imported": True})
    assert got == {"focused": None, "scrolled": None}


@needs_node
def test_a_child_cards_flag_banner_carries_the_same_context():
    got = _node(two_sections(), "openAll(); out(cardOf(5));")
    m = re.search(r'<ul class="lc-flags"><li class="lc-flags-ctx" id="fctx5">(.*?)</li>', got)
    assert m, "the banner opens with where the line is"
    assert text(m.group(1)) == f"C 3.a {trunc(CLAUSE_C, 28)} › 2Kg"


# ═══ B. Every resolver of parent_item_no ════════════════════════════════════

@pytest.fixture()
def clean(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["_boq_seeded"] = False
    yield client
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


def _saved_two_section_boq() -> dict:
    """A and C both carry item 3, each with its own children; B carries item 5
    TWICE, each with a child — saved-record shape, with line ids."""
    def ln(n, ino, sec, qty=10, header=False, parent="", desc=None):
        li = boq_line(ino, qty, section=sec, header=header, line_id=lid(n))
        li["parent_item_no"] = parent
        li["description"] = desc or f"{sec} {ino}"
        return li
    lines = [
        ln(1, "3", "A", 0, True, desc="A-three clause"),
        ln(2, "3.a", "A", parent="3"), ln(3, "3.b", "A", parent="3"),
        ln(7, "5", "B", 0, True, desc="First five clause"), ln(8, "5.a", "B", parent="5"),
        ln(9, "5", "B", 0, True, desc="Second five clause"), ln(10, "5.a", "B", parent="5"),
        ln(4, "3", "C", 0, True, desc="C-three clause"),
        ln(5, "3.a", "C", parent="3"), ln(6, "3.b", "C", parent="3"),
    ]
    make_boq("two", lines)
    rec = STORE["boqs"]["two"]
    rec["sections"] = [{"code": c, "title": c, "areas": []} for c in ("A", "B", "C")]
    return rec


def test_every_server_resolver_attaches_each_child_to_its_own_sections_parent(clean):
    rec = _saved_two_section_boq()
    want = {lid(1): [lid(2), lid(3)], lid(7): [lid(8)], lid(9): [lid(10)],
            lid(4): [lid(5), lid(6)]}
    assert boqpick.families(rec) == want            # DC, draft PO, PO, measurement
    assert ra._families(rec) == want                # the RA claim grid

    def picked(*ids):
        raw = json.dumps({"lines": [{"line_id": i, "qty": "1"} for i in ids]})
        items, err = boqpick.picked_lines(raw, rec, empty_msg="none", cap_msg="cap")
        assert err == ""
        return [(r["line_id"], r["is_header"]) for r in items]

    # A ticked C 3.a carries C's clause and never A's.
    assert picked(lid(5)) == [(lid(4), True), (lid(5), False)]
    assert picked(lid(2)) == [(lid(1), True), (lid(2), False)]
    # A repeated number carries only the child's own header.
    assert picked(lid(8)) == [(lid(7), True), (lid(8), False)]
    assert picked(lid(10)) == [(lid(9), True), (lid(10), False)]


def test_the_ra_print_heads_each_claim_with_its_own_sections_clause(clean):
    """/ra/print is the one print-side reader, and the tax invoice must head
    C 3.a with C's clause. The repeated number is the case the old lookup
    (a dict that kept the LAST header of a number) printed wrongly."""
    rec = _saved_two_section_boq()
    by_lid = {li["line_id"]: li for li in rec["line_items"]}
    claims = []
    for n in (2, 5, 8, 10):
        c = claim(by_lid[lid(n)]["item_no"], 1, rate=100.0)
        c["line_id"] = lid(n)
        claims.append(c)
    make_bill("rtwo", "two", 1, "supply", claims)
    page = clean.get("/ra/print/rtwo?copy=original").get_data(as_text=True)
    order = ["A-three clause", "C-three clause", "First five clause", "Second five clause"]
    at = [page.find(o) for o in order]
    assert -1 not in at, dict(zip(order, at))
    assert at == sorted(at), "each clause heads its own claim, in claim order"
    assert all(page.count(o) == 1 for o in order)


@needs_node
def test_the_editor_folds_each_child_under_its_own_sections_parent(clean):
    rec = _saved_two_section_boq()
    boot, _prefill = BQ._form_payload_from(rec)
    got = _node(boot, "out({a: childrenOf(0), b1: childrenOf(3), b2: childrenOf(5),"
                      " c: childrenOf(7)});")
    assert got == {"a": [1, 2], "b1": [4], "b2": [6], "c": [8, 9]}


def _res_line(row, kind, sec, item, parent, header, desc, make="", **kw):
    d = {"row": row, "kind": kind, "item_no": item, "parent_item_no": parent,
         "item_src": "", "section": sec, "is_header": header, "description": desc,
         "unit": "", "make": make, "qty": None, "supply_base_rate": None,
         "escalation_pct": None, "supply_rate": None, "install_base_rate": None,
         "install_escalation_pct": None, "install_rate": None, "lump_sum": False,
         "flags": [], "needs": [], "block": False}
    d.update(kw)
    return d


def test_the_importer_folds_spec_text_into_its_own_sections_parent():
    """`boqimport.editor_model()` folds a spec-text row into its parent: by
    section, and on a repeated number into the nearest one above."""
    result = {"sections": [{"code": "A", "title": "Hydrant"}, {"code": "B", "title": "B"},
                           {"code": "C", "title": "Extinguishers"}],
              "lines": [
                  _res_line(5, "header", "A", "3", "", True, "A clause"),
                  _res_line(6, "spec_text", "A", "", "3", True, "A words", make="Jindal"),
                  _res_line(7, "sub_item", "A", "3.a", "3", False, "150 mm", qty=10.0),
                  _res_line(8, "header", "B", "5", "", True, "First five"),
                  _res_line(9, "spec_text", "B", "", "5", True, "first words"),
                  _res_line(10, "header", "B", "5", "", True, "Second five"),
                  _res_line(11, "spec_text", "B", "", "5", True, "second words"),
                  _res_line(12, "header", "C", "3", "", True, "C clause"),
                  _res_line(13, "spec_text", "C", "", "3", True, "C words", make="KANEX"),
                  _res_line(14, "sub_item", "C", "3.a", "3", False, "2Kg", qty=350.0),
              ]}
    heads = {(l["section"], l["description"].split("\n")[0]): l
             for l in boqimport.editor_model(result)["lines"] if l["is_header"]}
    assert heads[("A", "A clause")]["description"] == "A clause\nA words"
    assert heads[("A", "A clause")]["remark"] == "Make: Jindal"
    assert heads[("C", "C clause")]["description"] == "C clause\nC words"
    assert heads[("C", "C clause")]["remark"] == "Make: KANEX"
    assert heads[("B", "First five")]["description"] == "First five\nfirst words"
    assert heads[("B", "Second five")]["description"] == "Second five\nsecond words"


# ═══ C. "Not priced" is an answer ═══════════════════════════════════════════

RATE_CASES = [("", False), ("0", True), ("0.00", True), (" 0 ", True), ("-", False),
              ("abc", False), ("-1", False), ("75", True), ("1,200", True)]


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: a
#   blank rate is a valid saved state, so `_need_met()` and the rate flag it
#   answered are gone; what is left is `line_problems()`, which marks only a
#   box that is WRONG. A blank and a "-" moved from "asks" to "fine"; text and
#   a negative are still marked.
#   The test as it stood:
#   @pytest.mark.parametrize("value,met", RATE_CASES)
#   def test_any_typed_number_answers_a_rate_flag_and_a_blank_does_not(value, met):
#       for f in ("supply_rate", "install_rate"):
#           assert BQ._need_met({f: value}, f, []) is met, (f, value)
#       assert BQ._need_met({"supply_rate": value, "install_rate": ""}, "rate", []) is met
#       assert BQ._need_met({"supply_rate": "", "install_rate": value}, "rate", []) is met

RATE_CASES_AS_IS = [("", True), ("0", True), ("0.00", True), (" 0 ", True), ("-", True),
                    ("abc", False), ("-1", False), ("75", True), ("1,200", True)]


@pytest.mark.parametrize("value,met", RATE_CASES_AS_IS)
def test_any_typed_number_answers_a_rate_flag_and_a_blank_does_not(value, met):
    """A rate box is wrong only when it holds TEXT or a negative figure (A3):
    a blank — or the client's "-" — is a valid answer and never marked."""
    for f in ("supply_rate", "install_rate"):
        probs = BQ.line_problems({"section": "A", f: value}, {"A": {"areas": []}})
        assert (f not in probs) is met, (f, value, probs)


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: a
#   blank quantity saves blank (§7 gap 42, closed) and is never asked for; the
#   "greater than 0" rule the import's need used is gone.
#   The test as it stood:
#   def test_the_quantity_rule_did_not_move():
#       """Only the RATE rule changed: a quantity still needs a figure above 0."""
#       assert BQ._need_met({"total_qty": "0"}, "total_qty", []) is False
#       assert BQ._need_met({"total_qty": "3"}, "total_qty", []) is True

def test_the_quantity_rule_did_not_move():
    """A blank quantity and a 0 are both valid (A3); text and a negative are not."""
    def wrong(v):
        return "total_qty" in BQ.line_problems({"section": "A", "total_qty": v},
                                               {"A": {"areas": []}})
    assert [wrong(v) for v in ("", "0", "3", "x", "-2")] == [False, False, False, True, True]


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: the
#   rule held in step is now `line_problems()` / `errMet()` — a WRONG box —
#   since `_need_met()` / `needMet()` are gone with the need.
#   The test as it stood:
#   @needs_node
#   def test_python_and_js_agree_on_the_rate_rule():
#       cases = [{"supply_rate": v, "install_rate": w} for v, _m in RATE_CASES
#                for w in ("", "0", "5")]
#       fields = ["supply_rate", "install_rate", "rate"]
#       py = [[BQ._need_met(c, f, []) for f in fields] for c in cases]
#       got = _node({"sections": [], "lines": []},
#                   "out(" + json.dumps(cases) + ".map(function (c) { return "
#                   + json.dumps(fields) + ".map(function (f) { return needMet(c, f); }); }));")
#       assert got == py

@needs_node
def test_python_and_js_agree_on_the_rate_rule():
    cases = [{"section": "A", "supply_rate": v, "install_rate": w}
             for v, _m in RATE_CASES_AS_IS for w in ("", "0", "5", "x")]
    fields = ["supply_rate", "install_rate"]
    by_code = {"A": {"areas": []}}
    py = [[f not in BQ.line_problems(c, by_code) for f in fields] for c in cases]
    got = _node({"sections": [{"code": "A", "title": "", "areas": []}], "lines": []},
                "out(" + json.dumps(cases) + ".map(function (c) { return "
                + json.dumps(fields) + ".map(function (f) { return errMet(c, f); }); }));")
    assert got == py


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3
#   removes the "Not priced (₹0)" button and the grey chip: a blank rate is a
#   valid answer, so there is nothing to answer with 0.
#   The test as it stood:
#   @needs_node
#   def test_the_not_priced_button_answers_its_flag_and_chips_the_line():
#       got = _node(two_sections(), """
#         var before = needList().length;
#         var btnShown = cardOf(5).indexOf('id="np5-supply_rate" onclick') >= 0;
#         fire(/onclick="(setNotPriced\\(5,&quot;supply_rate&quot;\\))"/);
#         out({before: before, btnShown: btnShown, after: needList().length,
#              rate: MODEL.lines[5].supply_rate, install: MODEL.lines[5].install_rate,
#              card: cardOf(5), bar: STUB['needs-bar'].innerHTML, np: isNotPriced(MODEL.lines[5])});
#       """, guide={"imported": True})
#       assert got["before"] == 2 and got["btnShown"]
#       assert got["after"] == 1
#       assert got["rate"] == "0" and got["install"] == "", "only the flagged track is typed"
#       assert got["np"] is True
#       assert '<span class="chip-np"' in got["card"] and ">not priced</span>" in got["card"]
#       assert 'id="np5-supply_rate" style="display:none;"' in got["card"], "answered: hidden"

@needs_node
def test_the_not_priced_button_answers_its_flag_and_chips_the_line():
    """No "Not priced (₹0)" button and no chip: a blank rate needs no answer."""
    got = _node(two_sections(), """
      openAll();
      out({card: cardOf(5), n: needList().length, fn: typeof setNotPriced,
           rate: MODEL.lines[5].supply_rate});
    """, guide={"imported": True})
    assert "np5-" not in got["card"] and "chip-np" not in got["card"]
    assert got["n"] == 0 and got["fn"] == "undefined" and got["rate"] == ""


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: a
#   blank no longer "brings the flag back" — there is no flag on a blank.
#   The test as it stood:
#   @needs_node
#   def test_typing_0_by_hand_is_the_same_answer_and_a_blank_brings_the_flag_back():
#       got = _node(two_sections(), """
#         openAll();
#         setLine(6, 'install_rate', '0');
#         var zero = [needList().length, isNotPriced(MODEL.lines[6]),
#                     document.getElementById('nps6').innerHTML,
#                     document.getElementById('np6-supply_rate').style.display];
#         setLine(6, 'install_rate', '');
#         var blank = [needList().length, isNotPriced(MODEL.lines[6]),
#                      document.getElementById('np6-supply_rate').style.display];
#         setLine(6, 'install_rate', '450');
#         out({zero: zero, blank: blank, priced: [needList().length, isNotPriced(MODEL.lines[6])]});
#       """)
#       assert got["zero"][:2] == [1, True] and "not priced" in got["zero"][2]
#       assert got["zero"][3] == "none", "the button hides once answered"
#       assert got["blank"] == [2, False, ""], "a blank is still a question"
#       assert got["priced"] == [1, False], "a real rate answers it and is not 'not priced'"

@needs_node
def test_typing_0_by_hand_is_the_same_answer_and_a_blank_brings_the_flag_back():
    """A 0, a blank and a figure are all valid; none is ever marked (A3)."""
    got = _node(two_sections(), """
      openAll();
      var seen = [];
      ['0', '', '450'].forEach(function (v) {
        setLine(6, 'install_rate', v);
        seen.push([needList().length, (LF['6:install_rate'] || {cls: {}}).cls.needs || 0]);
      });
      out(seen);
    """)
    assert got == [[0, 0], [0, 0], [0, 0]]


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: an
#   import's `_need` on either track is ignored — no button and no ring.
#   The test as it stood:
#   @needs_node
#   def test_a_track_flag_gets_its_button_on_that_track():
#       model = two_sections()
#       model["lines"][5]["_need"] = [{"f": "install_rate", "m": "Row 70: installation amount"}]
#       got = _node(model, """
#         openAll();
#         var c = cardOf(5);
#         fire(/onclick="(setNotPriced\\(5,&quot;install_rate&quot;\\))"/);
#         out({hasInstall: c.indexOf('id="np5-install_rate"') >= 0,
#              hasSupply: c.indexOf('id="np5-supply_rate"') >= 0,
#              install: MODEL.lines[5].install_rate, supply: MODEL.lines[5].supply_rate});
#       """)
#       assert got == {"hasInstall": True, "hasSupply": False, "install": "0", "supply": ""}

@needs_node
def test_a_track_flag_gets_its_button_on_that_track():
    model = two_sections()
    model["lines"][5]["_need"] = [{"f": "install_rate", "m": "Row 70: installation amount"}]
    got = _node(model, """
      openAll();
      var c = cardOf(5);
      out({hasInstall: c.indexOf('id="np5-install_rate"') >= 0,
           hasSupply: c.indexOf('id="np5-supply_rate"') >= 0,
           ringed: c.indexOf('class="needs"') >= 0});
    """)
    assert got == {"hasInstall": False, "hasSupply": False, "ringed": False}


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3/A4:
#   the two blank rates are saved BLANK without being answered (they were saved
#   as 0 after "Not priced"), and the view's amber note is the quiet one.
#   The test as it stood:
#   @needs_node
#   def test_every_flag_answered_not_priced_reads_all_answered_and_saves(clean):
#       """The whole path: both flags answered with the button, the bar reads
#       "All answered · 2 not priced (₹0) · review and save", saveJSON() posts,
#       the server saves (302), and /boq/view names the lines in its note."""
#       got = _node(two_sections(), """
#         var calls = [], re = /onclick="(setNotPriced\\([0-9]+,&quot;[a-z_]+&quot;\\))"/g, m;
#         while ((m = re.exec(editorHtml())) !== null) calls.push(m[1].replace(/&quot;/g, '"'));
#         calls.forEach(function (c) { eval(c); });
#         var ok = saveJSON();
#         out({calls: calls.length, left: needList().length, bar: STUB['needs-bar'].innerHTML,
#              ok: ok, posted: STUB['boq_json'].value});
#       """, guide={"imported": True})
#       assert got["calls"] == 2 and got["left"] == 0
#       assert text(got["bar"]).startswith("✓ All answered · 2 not priced (₹0) · review and save")
#       assert got["ok"] is True
#
#       before = set(STORE["boqs"])
#       r = clean.post("/boq/create", data={
#           "date": "2026-09-30", "project_name": "Jamnagar", "account_name": "Prudent",
#           "rev_no": "0", "boq_json": got["posted"]})
#       assert r.status_code == 302
#       (bid,) = set(STORE["boqs"]) - before
#       saved = {(l["section"], l["item_no"]): l for l in STORE["boqs"][bid]["line_items"]}
#       for key, qty in ((("C", "3.a"), 350.0), (("C", "3.b"), 20.0)):
#           li = saved[key]
#           assert li["total_qty"] == qty and li["supply_rate"] == 0.0
#           assert li["install_rate"] == 0.0 and li["supply_amount"] == 0.0
#       assert not any(k.startswith("_") for l in saved.values() for k in l)
#
#       view = clean.get(f"/boq/view/{bid}").get_data(as_text=True)
#       note = re.search(r'<div class="form-hint unpriced-note" id="unpriced-note">(.*?)</div>',
#                        view, re.S)
#       assert note, "the view carries the note"
#       words = text(note.group(1))
#       assert words.startswith("⚠ 3 lines have a quantity but no rate — A 3.b · C 3.a, 3.b.")
#       assert "Nothing is blocked" in words

@needs_node
def test_every_flag_answered_not_priced_reads_all_answered_and_saves(clean):
    """The whole path, as it is: the blank rates are NOT answered — saveJSON()
    posts at once, the server saves them ABSENT (never 0), and /boq/view says
    so in its quiet note."""
    got = _node(two_sections(), """
      var ok = saveJSON();
      out({ok: ok, posted: STUB['boq_json'].value, bar: STUB['needs-bar'].innerHTML});
    """, guide={"imported": True})
    assert got["ok"] is True and got["bar"] == ""

    before = set(STORE["boqs"])
    r = clean.post("/boq/create", data={
        "date": "2026-09-30", "project_name": "Jamnagar", "account_name": "Prudent",
        "rev_no": "0", "boq_json": got["posted"]})
    assert r.status_code == 302
    (bid,) = set(STORE["boqs"]) - before
    saved = {(l["section"], l["item_no"]): l for l in STORE["boqs"][bid]["line_items"]}
    for key, qty in ((("C", "3.a"), 350.0), (("C", "3.b"), 20.0)):
        li = saved[key]
        assert li["total_qty"] == qty and li["supply_rate"] is None
        assert li["install_rate"] is None and li["supply_amount"] is None
    assert not any(k.startswith("_") for l in saved.values() for k in l)

    view = clean.get(f"/boq/view/{bid}").get_data(as_text=True)
    note = re.search(r'<div class="quiet-note" id="blank-note">(.*?)</div>', view, re.S)
    assert note and text(note.group(1)) == "3 lines have no rate."
    assert 'id="unpriced-note"' not in view


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3:
#   `unpriced_lines()` and its amber note are replaced by `lines_not_priced()`
#   / `lines_without_qty()` and the quiet note.
#   The test as it stood:
#   def test_the_view_note_is_absent_when_every_line_is_priced(clean):
#       rec = _saved_two_section_boq()
#       assert BQ.unpriced_lines(rec) == []
#       view = clean.get("/boq/view/two").get_data(as_text=True)
#       assert 'id="unpriced-note"' not in view

def test_the_view_note_is_absent_when_every_line_is_priced(clean):
    rec = _saved_two_section_boq()
    assert BQ.lines_not_priced(rec) == [] and BQ.lines_without_qty(rec) == []
    view = clean.get("/boq/view/two").get_data(as_text=True)
    assert 'id="unpriced-note"' not in view and 'id="blank-note"' not in view


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A1/A3:
#   "no rate" is a rate left BLANK (`None`), not a 0 — a 0 is a rate, priced at
#   nil — and the note counts blank quantities too, quietly.
#   The test as it stood:
#   def test_the_view_note_counts_quantity_with_no_rate_on_either_track(clean):
#       rec = _saved_two_section_boq()
#       by = {li["line_id"]: li for li in rec["line_items"]}
#       by[lid(2)].update(supply_rate=0.0, install_rate=0.0)          # A 3.a: unpriced
#       by[lid(5)].update(supply_rate=0.0, install_rate=35.0)         # C 3.a: install only — priced
#       by[lid(6)].update(supply_rate=0.0, install_rate=0.0, total_qty=0.0)  # no quantity — not counted
#       assert BQ.unpriced_lines(rec) == [("A", "3.a")]
#       view = clean.get("/boq/view/two").get_data(as_text=True)
#       assert "<b>1 line has a quantity but no rate</b>" in view

def test_the_view_note_counts_quantity_with_no_rate_on_either_track(clean):
    rec = _saved_two_section_boq()
    by = {li["line_id"]: li for li in rec["line_items"]}
    by[lid(2)].update(supply_rate=None, install_rate=None)            # A 3.a: no rate
    by[lid(5)].update(supply_rate=None, install_rate=35.0)            # C 3.a: install only — priced
    by[lid(6)].update(supply_rate=None, install_rate=None, total_qty=None)  # neither
    by[lid(7)].update(supply_rate=0.0, install_rate=0.0)              # a 0 is a rate
    assert BQ.lines_not_priced(rec) == [("A", "3.a"), ("C", "3.b")]
    assert BQ.lines_without_qty(rec) == [("C", "3.b")]
    view = clean.get("/boq/view/two").get_data(as_text=True)
    assert '<div class="quiet-note" id="blank-note">2 lines have no rate, 1 line has no quantity.</div>' in view


# ═══ D. Units the sheet did not give ════════════════════════════════════════

# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3
#   removes the soft amber outline on a blank imported unit and the bar's "· N
#   units blank" — each a mark on a blank.
#   The test as it stood:
#   @needs_node
#   def test_a_blank_imported_unit_is_a_soft_outline_outside_the_needs_count():
#       got = _node(two_sections(), """
#         openAll();
#         var c7 = cardOf(7), c3 = cardOf(3), c6 = cardOf(6);
#         var before = [unitsBlank(), needList().length, STUB['needs-bar'].innerHTML];
#         setLine(7, 'unit', 'Nos');
#         var lf = LF['7:unit'];
#         out({c7: c7, c3: c3, c6: c6, before: before,
#              after: [unitsBlank(), needList().length, STUB['needs-bar'].innerHTML],
#              cleared: lf && !lf.cls['unit-soft']});
#       """)
#       unit_input = r'<label>Unit</label><input type="text" value="" placeholder="unit"[^>]*data-lf="7:unit" class="unit-soft"'
#       assert re.search(unit_input, got["c7"]), "imported, blank unit: soft outline"
#       assert "unit-soft" not in got["c3"], "a hand-typed line is never outlined"
#       assert "unit-soft" not in got["c6"], "an imported line WITH a unit is not outlined"
#       n_units, n_needs, bar = got["before"]
#       assert (n_units, n_needs) == (2, 2), "C 3.a and C 9.a; the header is not a line"
#       assert "2 fields need you · 2 units blank" in text(bar)
#       assert got["after"][:2] == [1, 2], "filling a unit never moves the needs count"
#       assert "· 1 unit blank" in text(got["after"][2])
#       assert got["cleared"] is True, "the outline clears as the unit is typed"

@needs_node
def test_a_blank_imported_unit_is_a_soft_outline_outside_the_needs_count():
    """A blank unit is a blank unit: no outline, no count (A3)."""
    got = _node(two_sections(), """
      openAll();
      out({c7: cardOf(7), n: needList().length, fn: typeof unitsBlank});
    """)
    assert "unit-soft" not in got["c7"]
    assert re.search(r'<label>Unit</label><input type="text" value="" placeholder="unit"', got["c7"])
    assert got["n"] == 0 and got["fn"] == "undefined"


@needs_node
def test_unit_for_all_sizes_fills_only_the_blank_ones():
    got = _node(two_sections(), """
      openAll();
      var band = cardOf(4);
      setKidUnit(4, 'Kg');
      var n = applyKidUnit(4);
      out({band: band, n: n, units: MODEL.lines.map(function (L) { return L.unit; })});
    """)
    assert re.search(r'<label>Unit for all <span id="kun4">2</span> sizes</label>'
                     r'<input type="text" value="" placeholder="unit"', got["band"])
    assert "Apply</button>" in got["band"]
    assert got["n"] == 1
    # C 3.a was blank and is filled; C 3.b's typed "Nos" is kept; A's children —
    # the OTHER item 3 — are untouched, blank or not.
    assert got["units"] == ["Nos", "", "Mtrs", "", "", "Kg", "Nos", ""]
    # ⚠ AMENDED 6 October 2026 — the §0 forty-fifth block, A3: the bar's
    #   "· N units blank" and `unitsBlank()` are gone (a mark on a blank).
    #   The assertion as it stood:
    #       assert got["blank"] == 1 and "· 1 unit blank" in text(got["bar"])


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: the
#   bar is gone, and with it the units note.
#   The test as it stood:
#   @needs_node
#   def test_the_bar_shows_the_units_note_even_with_nothing_to_answer():
#       model = two_sections()
#       for l in model["lines"]:
#           l.pop("_need", None)
#       got = _node(model, "out(STUB['needs-bar'].innerHTML);")
#       assert text(got) == "✓ All filled — review and save · 2 units blank"

@needs_node
def test_the_bar_shows_the_units_note_even_with_nothing_to_answer():
    model = two_sections()
    for l in model["lines"]:
        l.pop("_need", None)
    got = _node(model, "out(STUB['needs-bar'].innerHTML);")
    assert got == "", "there is no bar to carry a units note"


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3:
#   `unitsBlank()` and the bar's display are gone; what is held is that nothing
#   is drawn.
#   The test as it stood:
#   def test_a_plain_form_draws_no_units_note_and_no_outline():
#       """No `_row`, no import: the typed form is exactly what it was."""
#       if NODE is None:
#           pytest.skip("node not installed")
#       model = two_sections()
#       for l in model["lines"]:
#           for k in ("_row", "_need", "_flags"):
#               l.pop(k, None)
#       got = _node(model, "openAll(); out({h: editorHtml(), n: unitsBlank(),"
#                          " bar: STUB['needs-bar'].style.display});")
#       assert got["n"] == 0 and "unit-soft" not in got["h"] and got["bar"] == "none"

def test_a_plain_form_draws_no_units_note_and_no_outline():
    """No `_row`, no import: no outline — and an import gets none either now."""
    if NODE is None:
        pytest.skip("node not installed")
    model = two_sections()
    for l in model["lines"]:
        for k in ("_row", "_need", "_flags"):
            l.pop(k, None)
    got = _node(model, "openAll(); out({h: editorHtml(), bar: STUB['needs-bar'].innerHTML});")
    assert "unit-soft" not in got["h"] and got["bar"] == ""


def test_the_preview_says_when_the_sheet_has_no_unit_column(clean):
    openpyxl = pytest.importorskip("openpyxl")
    # A remembered layout would skip the preview; this test is about the preview.
    STORE.get("import_layouts", {}).clear()

    def upload(rows):
        wb = openpyxl.Workbook()
        for r in rows:
            wb.active.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        r = clean.post("/boq/import", data={"workbook": (io.BytesIO(buf.getvalue()), "t.xlsx")},
                       content_type="multipart/form-data")
        tok = r.headers["Location"].split("/boq/import/")[1].split("/")[0].split("#")[0]
        return clean.get(f"/boq/import/{tok}").get_data(as_text=True)

    no_unit = upload([["Sr. No.", "Description", "Qty", "Supply Rate", "Supply Amount"],
                      ["1", "Pipe", 10, 100, 1000], ["2", "Valve", 2, 50, 100]])
    assert ("This sheet has no Unit column: <b>2</b> lines have no unit "
            "(fill on the form)") in no_unit
    with_unit = upload([["Sr. No.", "Description", "Qty", "Unit", "Supply Rate",
                         "Supply Amount"], ["1", "Pipe", 10, "", 100, 1000]])
    assert "has no Unit column" not in with_unit, "a Unit column is mapped: no line"


# ═══ E. Placeholders on an imported line ════════════════════════════════════

def _ph(card: str, aria: str) -> str:
    m = re.search(rf'placeholder="([^"]*)" aria-label="{aria}"', card)
    return m.group(1) if m else None


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: no
#   rate box is "ringed" for a blank any more, so none says "type rate" — the
#   supply unit rate reads "rate" like the rest.
#   The test as it stood:
#   @needs_node
#   def test_an_imported_lines_blank_boxes_say_what_goes_in_them_in_words():
#       got = _node(two_sections(), "openAll(); out({c: cardOf(5), plain: cardOf(3)});")
#       c = got["c"]
#       assert [_ph(c, a) for a in ("Supply base rate", "Supply escalation %", "Supply unit rate",
#                                   "Installation base rate", "Installation escalation %",
#                                   "Installation unit rate")] == [
#           "rate", "esc %", "type rate", "rate", "esc %", "rate"]
#       assert re.search(r'<label>Unit</label><input type="text" value="" placeholder="unit"', c)
#       # The typed form keeps its examples.
#       p = got["plain"]
#       assert [_ph(p, a) for a in ("Supply base rate", "Supply escalation %", "Supply unit rate",
#                                   "Installation unit rate")] == ["1760  or  -", "15", "2024", "1200"]
#       assert re.search(r'<label>Unit</label><input type="text" value="" placeholder="Mtrs"', p)

@needs_node
def test_an_imported_lines_blank_boxes_say_what_goes_in_them_in_words():
    got = _node(two_sections(), "openAll(); out({c: cardOf(5), plain: cardOf(3)});")
    c = got["c"]
    assert [_ph(c, a) for a in ("Supply base rate", "Supply escalation %", "Supply unit rate",
                                "Installation base rate", "Installation escalation %",
                                "Installation unit rate")] == [
        "rate", "esc %", "rate", "rate", "esc %", "rate"]
    assert re.search(r'<label>Unit</label><input type="text" value="" placeholder="unit"', c)
    # The typed form keeps its examples.
    p = got["plain"]
    assert [_ph(p, a) for a in ("Supply base rate", "Supply escalation %", "Supply unit rate",
                                "Installation unit rate")] == ["1760  or  -", "15", "2024", "1200"]
    assert re.search(r'<label>Unit</label><input type="text" value="" placeholder="Mtrs"', p)


