"""
The BOQ picker's fill rules, executed.

Everything else in this suite tests Python. The rule that matters most on this
form — **a catalogue rate fills an empty box and never overwrites a typed
one** — lives in JavaScript, and asserting that a string appears in the page
source only proves the code shipped, not that it behaves.

So this file pulls the real `fillFromSpec` / `fillFromVariant` /
`insertFamily` out of `boq._BOQ_JS`, injects the same payload the page gets
from `_spec_catalog_json()`, and runs them under Node. If Node is not
installed the file skips rather than failing — it is a sharper test, not a
required toolchain.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


def _run(script: str, seeded_client):
    """Execute the page's own JS with a stub DOM, and return its result."""
    import boq

    payload = boq._spec_catalog_json()

    # The page's JS, with the two hooks it needs from a browser stubbed. Only
    # the DOM is faked; every function under test is the shipped source.
    harness = (
        "var BOQ_SPECS_JSON = " + payload + ";\n"
        "var document = { body: {}, getElementById: function(id) "
        "{ return STUB[id] || null; } };\n"
        "var window = { scrollTo: function(){}, confirm: function(){ return true; } };\n"
        "var STUB = { 'bulk-spec': {value:'', innerHTML:''}, "
        "'bulk-section': {value:'A', innerHTML:''}, "
        "'line-editor': {innerHTML:''}, 'sec-editor': {innerHTML:''} };\n"
    )

    js = boq._BOQ_JS
    js = js.replace("<script>", "").replace("</script>", "")
    js = js.replace("BOQ_SPECS", "BOQ_SPECS_JSON")
    js = js.replace("BOQ_BOOT", json.dumps(
        {"sections": [{"code": "A", "title": "Sprinklers", "areas": ["L0"]}],
         "lines": []}))
    js = js.replace("BOQ_ADDR", "{}")
    # The two render passes at the foot of the file need a DOM; the stub has
    # the elements they write into, so they run as-is.

    # Written to a file rather than passed to `node -e`: the payload is 56
    # clauses, several over a kilobyte, and Windows caps a command line at
    # 32767 characters.
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf8") as fh:
        fh.write(harness + js + "\n" + script)
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


def _spec_id(code):
    import boq
    return [sid for sid, s in json.loads(boq._spec_catalog_json()).items()
            if s["code"] == code][0]


def test_picking_a_spec_fills_text_and_tax_classification(seeded):
    sid = _spec_id("PIPE-MS-C-1239-AG")
    res = _run(f"""
        MODEL.lines.push(blankLine());
        fillFromSpec(0, '{sid}');
        console.log(JSON.stringify(MODEL.lines[0]));
    """, seeded)
    assert len(res["description"]) > 1000          # the full clause
    assert res["supply_hsn"] == "73063090"
    assert res["install_sac"] == "995462"
    assert res["supply_gst_rate"] == "18"
    assert res["install_gst_rate"] == "18"
    # A sized spec leaves the unit alone — it lives on the variant.
    assert res["unit"] == ""


def test_picking_a_variant_fills_unit_and_suggests_both_base_rates(seeded):
    sid = _spec_id("PIPE-MS-C-1239-AG")
    res = _run(f"""
        MODEL.lines.push(blankLine());
        fillFromSpec(0, '{sid}');
        fillFromVariant(0, '150 mm dia');
        console.log(JSON.stringify(MODEL.lines[0]));
    """, seeded)
    assert res["unit"] == "Mtrs"
    assert res["supply_base_rate"] == "1760"
    assert res["install_base_rate"] == "1200"
    assert res["description"] == "150 mm dia"      # the child row's own text


def test_an_unsized_spec_fills_its_unit_immediately(seeded):
    """With no size still to choose there is nothing to wait for."""
    sid = _spec_id("HYD-FIREMANS-AXE")
    res = _run(f"""
        MODEL.lines.push(blankLine());
        fillFromSpec(0, '{sid}');
        console.log(JSON.stringify(MODEL.lines[0]));
    """, seeded)
    assert res["unit"] == "Nos."
    assert "firemans axe" in res["description"]


def test_a_typed_rate_is_never_overwritten(seeded):
    """
    THE rule. purchase.py's fillRate precedent, handover §4.2 rule 4: the
    project's rate basis is the truth and the library only suggests.
    """
    sid = _spec_id("PIPE-MS-C-1239-AG")
    res = _run(f"""
        MODEL.lines.push(blankLine());
        MODEL.lines[0].supply_base_rate = '999';
        MODEL.lines[0].unit = 'Rmt';
        fillFromSpec(0, '{sid}');
        fillFromVariant(0, '150 mm dia');
        console.log(JSON.stringify(MODEL.lines[0]));
    """, seeded)
    assert res["supply_base_rate"] == "999"        # kept
    assert res["unit"] == "Rmt"                    # kept
    assert res["install_base_rate"] == "1200"      # was empty, so filled


def test_a_typed_description_is_never_overwritten(seeded):
    sid = _spec_id("PIPE-MS-C-1239-AG")
    res = _run(f"""
        MODEL.lines.push(blankLine());
        MODEL.lines[0].description = 'our own wording';
        fillFromSpec(0, '{sid}');
        fillFromVariant(0, '150 mm dia');
        console.log(JSON.stringify(MODEL.lines[0]));
    """, seeded)
    assert res["description"] == "our own wording"


def test_insert_family_builds_a_header_and_one_child_per_size(seeded):
    sid = _spec_id("PIPE-MS-C-1239-AG")
    res = _run(f"""
        STUB['bulk-spec'].value = '{sid}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        console.log(JSON.stringify(MODEL.lines));
    """, seeded)
    assert len(res) == 10                          # 1 header + 9 sizes
    head = res[0]
    assert head["is_header"] is True
    assert head["item_no"] == "1"
    assert len(head["description"]) > 1000
    kids = res[1:]
    assert [k["item_no"] for k in kids] == [
        "1.a", "1.b", "1.c", "1.d", "1.e", "1.f", "1.g", "1.h", "1.i"]
    assert all(k["parent_item_no"] == "1" for k in kids)
    assert kids[0]["unit"] == "Mtrs"
    assert all(not k["is_header"] for k in kids)

    # 24.a (200 mm dia) carries "-" as its base rate in the source — the rate
    # was negotiated directly rather than escalated — so there is nothing to
    # suggest and the box is left empty rather than filled with a zero.
    assert kids[0]["supply_base_rate"] == ""
    # 24.b (150 mm dia) does have one, and it comes across.
    assert kids[1]["supply_base_rate"] == "1760"
    assert kids[1]["install_base_rate"] == "1200"


def test_insert_family_numbers_after_what_is_already_there(seeded):
    """N is the next whole number free in that section — 24 after 1..23."""
    sid = _spec_id("PIPE-MS-C-1239-AG")
    res = _run(f"""
        for (var n = 1; n <= 23; n++) {{
          var L = blankLine(); L.section = 'A'; L.item_no = String(n);
          MODEL.lines.push(L);
        }}
        STUB['bulk-spec'].value = '{sid}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        console.log(JSON.stringify(MODEL.lines.slice(23).map(function(l){{
          return l.item_no; }})));
    """, seeded)
    assert res == ["24", "24.a", "24.b", "24.c", "24.d", "24.e",
                   "24.f", "24.g", "24.h", "24.i"]


def test_insert_family_on_an_unsized_spec_makes_one_plain_line(seeded):
    sid = _spec_id("HYD-FIREMANS-AXE")
    res = _run(f"""
        STUB['bulk-spec'].value = '{sid}';
        STUB['bulk-section'].value = 'A';
        insertFamily();
        console.log(JSON.stringify(MODEL.lines));
    """, seeded)
    assert len(res) == 1
    assert res[0]["is_header"] is False
    assert res[0]["parent_item_no"] == ""
    assert res[0]["unit"] == "Nos."
