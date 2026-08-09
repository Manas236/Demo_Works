"""
The RA claim grid's family fold, executed — against the real rendered page.

The property under test is the one the fold could plausibly break and the one
that would be silent if it did:

    **What gets POSTed does not depend on what is open.**

An operator expands specification family 4, enters quantities on 4.1 to 4.8,
folds it again to keep scrolling, and submits. If folding could drop those
lines the claim would go out short and nothing on the page would say so. So
this drives the real `ra._RA_JS` over a DOM built from the real
`/ra/create` HTML, folds and unfolds, and diffs `ra_json` byte for byte.

Modeled on `tests/test_picker_js.py`, and for its reasons — a harness that
calls the functions directly does not test that the rendered `<tr onclick=…>`
is wired to them, and one that starts from a synthetic model does not test the
markup the server actually emits. Both the element ids and the family map here
are scraped out of the page.

Skips when Node is absent, like its sibling.
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


# A DOM small enough to read and large enough for everything _RA_JS touches.
_HARNESS = """
function Elem(attrs) {
  this.attrs = attrs || {};
  this.value = this.attrs.value || '';
  this.style = { display: this.attrs.__display || '' };
  this.textContent = '';
  this.className = '';
  this.parentNode = { className: '' };
}
Elem.prototype.getAttribute = function (k) {
  return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
};
Elem.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };

var STUB = {};
for (var __id in ELEMS) { STUB[__id] = new Elem(ELEMS[__id]); }
var document = { getElementById: function (id) { return STUB[id] || null; } };
var window = {};
"""

_DRIVER = """
/* Fire a header's rendered onclick the way a browser would. Pulled out of the
   page HTML, so an unwired or mis-argumented handler fails here. */
function fireHeader(hlid) {
  var re = new RegExp('id="head_' + hlid + '"[^>]*onclick="([^"]*)"');
  var m = re.exec(PAGE);
  if (!m) throw new Error('header ' + hlid + ' has no wired onclick');
  eval(m[1].replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
}

function typeInto(lid, qty, rate) {
  var q = el('q_' + lid);
  if (!q) throw new Error('no quantity input for ' + lid);
  q.value = String(qty);
  if (rate !== undefined) el('r_' + lid).value = String(rate);
  recalc(lid);
}

function payload() { saveJSON(); return el('ra_json').value; }

function hiddenIds() {
  var out = [];
  for (var i = 0; i < LINE_IDS.length; i++) {
    var row = el('row_' + LINE_IDS[i]);
    if (row && row.style.display === 'none') out.push(LINE_IDS[i]);
  }
  return out.sort();
}

function inputCount() {
  var n = 0;
  for (var i = 0; i < LINE_IDS.length; i++) if (el('q_' + LINE_IDS[i])) n++;
  return n;
}

function out(o) { console.log(JSON.stringify(o)); }
"""

_ATTR = re.compile(r'([a-zA-Z-]+)="([^"]*)"')


def _scrape(html: str) -> dict:
    """
    Every element `_RA_JS` can address, built out of the rendered page.

    Scraped rather than declared: if the server stops emitting `data-open`, or
    renames a chevron id, these tests go red instead of quietly exercising a
    DOM that no longer resembles the page.
    """
    elems = {}
    for tag in re.finditer(r"<(tr|td|input|span|p)\b([^>]*)>", html):
        attrs = dict(_ATTR.findall(tag.group(2)))
        eid = attrs.get("id")
        if not eid:
            continue
        keep = {k: v for k, v in attrs.items() if k.startswith("data-")}
        if "value" in attrs:
            keep["value"] = attrs["value"]
        if "display:none" in (attrs.get("style") or "").replace(" ", ""):
            keep["__display"] = "none"
        elems[eid] = keep
    # `_RA_JS` writes to these three unconditionally on load.
    for eid in ("ra-total", "ra-count", "ra-over", "ra_json"):
        elems.setdefault(eid, {})
    return elems


def _session(html: str, script: str):
    import ra

    line_ids = re.search(r"var LINE_IDS = (\[.*?\]);", html, re.S).group(1)
    families = re.search(r"var FAMILIES = (\{.*?\});", html, re.S).group(1)

    js = ra._RA_JS.replace("<script>", "").replace("</script>", "")
    harness = (
        "var ELEMS = " + json.dumps(_scrape(html)) + ";\n"
        "var PAGE = " + json.dumps(html) + ";\n"
        + _HARNESS
        + "var LINE_IDS = " + line_ids + ";\n"
        + "var FAMILIES = " + families + ";\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf8") as fh:
        fh.write(harness + js + _DRIVER + "\n" + script)
        path = fh.name
    try:
        proc = subprocess.run(["node", path], capture_output=True,
                              text=True, timeout=30, encoding="utf8")
    finally:
        os.unlink(path)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture()
def sify_form(client):
    """The claim grid over the seeded 97-line Sify schedule — 10 families."""
    import boq as BQ
    from store import STORE

    BQ.ensure_demo_boq()
    bid = next(iter(STORE["boqs"]))
    res = client.get(f"/ra/create?boq={bid}&leg=supply")
    assert res.status_code == 200
    return res.get_data(as_text=True)


# ═══ Everything is on the page, folded or not ══════════════════════════════

def test_every_boq_line_has_its_inputs_whatever_is_folded(sify_form):
    res = _session(sify_form, """
        var start = inputCount(), startHidden = hiddenIds().length;
        expandAll();
        var open = inputCount(), openHidden = hiddenIds().length;
        collapseAll();
        out({lines: LINE_IDS.length, start: start, open: open,
             shut: inputCount(), startHidden: startHidden,
             openHidden: openHidden, shutHidden: hiddenIds().length});
    """)
    # 87 priced lines on the Sify schedule, 40 of them inside a family.
    assert res["lines"] == res["start"] == res["open"] == res["shut"] == 87
    assert res["startHidden"] == 40, "families should arrive folded"
    assert res["openHidden"] == 0
    assert res["shutHidden"] == 40


# ═══ The property ══════════════════════════════════════════════════════════

def test_folding_after_entry_does_not_change_the_post_body(sify_form):
    """
    The realistic sequence: open a family, enter against its children, fold it
    away to keep scrolling, submit.
    """
    res = _session(sify_form, """
        var hlid = Object.keys(FAMILIES)[0];
        fireHeader(hlid);                       /* the operator opens it */
        var kids = FAMILIES[hlid];
        for (var i = 0; i < kids.length; i++) typeInto(kids[i], i + 1, 100);
        typeInto(LINE_IDS[LINE_IDS.length - 1], 9, 250);   /* a top-level line */

        var expanded = payload();
        fireHeader(hlid);                       /* ...and folds it again */
        var folded = payload();
        collapseAll();
        var allShut = payload();
        expandAll();
        out({expanded: expanded, folded: folded, allShut: allShut,
             allOpen: payload(), kids: kids.length});
    """)
    assert res["kids"] == 8
    assert res["folded"] == res["expanded"]
    assert res["allShut"] == res["expanded"]
    assert res["allOpen"] == res["expanded"]

    posted = json.loads(res["expanded"])["lines"]
    assert len(posted) == 9
    assert all(float(row["qty"]) > 0 for row in posted)


def test_entry_into_a_folded_family_still_posts(sify_form):
    """
    The same invariant from the other side — the value is in the document, so
    it is in the payload, and visibility never came into it.
    """
    res = _session(sify_form, """
        var hlid = Object.keys(FAMILIES)[0], kids = FAMILIES[hlid];
        typeInto(kids[0], 5, 2024);             /* still folded */
        var folded = payload();
        expandAll();
        out({folded: folded, expanded: payload()});
    """)
    assert res["folded"] == res["expanded"]
    assert json.loads(res["folded"])["lines"][0]["qty"] == "5"


def test_a_round_trip_through_the_toggle_restores_the_page_exactly(sify_form):
    res = _session(sify_form, """
        var hlid = Object.keys(FAMILIES)[0];
        var before = hiddenIds();
        fireHeader(hlid); fireHeader(hlid);
        out({before: before, after: hiddenIds(),
             chev: el('chev_' + hlid).textContent,
             open: el('head_' + hlid).getAttribute('data-open')});
    """)
    assert res["after"] == res["before"]
    assert res["open"] == "0"
    assert res["chev"] == "▸"          # ▸ — shut


def test_the_toggle_folds_only_its_own_family(sify_form):
    """
    Item numbers restart per section and the client's section A carries item 17
    twice, so a fold keyed on anything but `line_id` would take the wrong rows
    with it. `_families()` keys on (section, item_no) and the DOM keys on the
    header's own id.
    """
    res = _session(sify_form, """
        var ids = Object.keys(FAMILIES);
        expandAll();
        fireHeader(ids[0]);
        out({hidden: hiddenIds().sort(), mine: FAMILIES[ids[0]].slice().sort()});
    """)
    assert res["hidden"] == res["mine"]


def test_the_over_claim_warning_still_fires_from_inside_a_folded_family(sify_form):
    """
    Folding is presentation. The keystroke arithmetic — the thing this form was
    sold on — runs on the row whether or not it is on screen.
    """
    res = _session(sify_form, """
        var hlid = Object.keys(FAMILIES)[0], kid = FAMILIES[hlid][0];
        var approved = parseFloat(el('row_' + kid).getAttribute('data-approved'));
        typeInto(kid, approved + 10, 2024);
        out({banner: el('ra-over').textContent,
             shown: el('ra-over').style.display,
             cell: el('q_' + kid).parentNode.className});
    """)
    assert "over the approved quantity" in res["banner"]
    assert res["shown"] == ""
    assert "cl-over" in res["cell"]
