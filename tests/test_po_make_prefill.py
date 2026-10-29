"""
Make prefills from the BOQ line's import remark — 29 October 2026,
CLIENT_CHANGES.md §0 **fifty-ninth** block, A3.

    on both the real PO and the Draft PO, Make prefills from the BOQ line,
    parsed from the Excel import remark. Parse only a clear explicit pattern
    found in the real import code and fixtures. Otherwise leave it blank.
    Never guess.

**This closes ABOUT.md §7 gap 81, which was OPEN BY INSTRUCTION.** The
fifty-third block said prefill from a make *field*; neither a BOQ line nor a
specification variant has one, and that is still true and still asserted
(`tests/test_po_make.py::test_no_boq_line_and_no_spec_variant_has_a_make_field_to_prefill_from`).
What changed is that Manas took the decision the gap was waiting for: read
`boqimport._with_make()`'s own output and nothing wider.

⚠ **The "never guess" half is the half with the tests.** Anything can be made
  to prefill; the work is in refusing prose that merely contains the word.
"""

import json

import pytest

import boq as BQ
import boqimport as BI
from store import STORE

VENDOR_ID = "b2000003-face-4000-8000-000000000003"


# ═══ 1. The pattern — exactly the importer's, and nothing wider ════════════

@pytest.mark.parametrize("remark,expected", [
    # What `boqimport._with_make()` actually writes.
    ("Make: Jindal",                       "Jindal"),
    ("Make: KANEX",                        "KANEX"),
    # With the sheet's own Remark column in front of it (R1's order).
    ("supplied loose; Make: Jindal",       "Jindal"),
    ("Rate only line; Make: Newage",       "Newage"),
    # Several, joined and never dropped — `makeOf()`'s rule.
    ("Make: Jindal; Make: Newage",         "Jindal / Newage"),
    ("a; Make: Jindal; b; Make: KANEX",    "Jindal / KANEX"),
    # The same brand twice is one brand.
    ("Make: Jindal; Make: Jindal",         "Jindal"),
    # Case and spacing, which the editor's own regex tolerates.
    ("make:  jindal  ",                    "jindal"),
    ("MAKE:Jindal",                        "Jindal"),
    # ── AND THE REFUSALS. Each of these is prose, not a field. ────────────
    ("",                                   ""),
    (None,                                 ""),
    ("pipe to be supplied, Make: as approved", ""),
    ("confirm the Make: with the client",   ""),
    ("no brand named here",                ""),
    ("Brand: Jindal",                      ""),
    ("Make Jindal",                        ""),
    ("MakeShift: Jindal",                  ""),
])
def test_the_pattern_reads_the_importers_own_output_and_nothing_wider(remark, expected):
    assert BQ.make_from_remark(remark) == expected


def test_the_anchor_is_what_refuses_prose():
    """
    ⚠ The load-bearing character is `(?:^|;)`. Without it the third refusal
    above becomes "as approved", which is the guess §7 gap 81 declined to
    make. Asserted as a pair so the reason is in the test and not only in a
    comment.
    """
    assert BQ.make_from_remark("Make: as approved") == "as approved"
    assert BQ.make_from_remark("pipe, Make: as approved") == ""


def test_it_reads_back_exactly_what_the_importer_writes():
    """
    ⚠ The round trip, against the writer itself rather than against a literal:
    the day `_with_make()` changes its separator or its label, this fails.
    """
    for make in ("Jindal", "KANEX", "Newage Industries", "TATA / GI"):
        assert BQ.make_from_remark(BI._with_make("", make)) == make
        assert BQ.make_from_remark(BI._with_make("an internal note", make)) == make
        assert BQ.make_from_remark(
            BI._with_notes(BI._with_make(BI._with_note("", "note"), make), None)) == make


def test_the_server_and_the_browser_run_the_same_pattern():
    """
    `boq.py`'s own `makeOf()` runs this regex in the editor. Two
    implementations of one pattern is how a prefill starts disagreeing with
    the strip above the line it came from.
    """
    import pathlib
    src = pathlib.Path(BQ.__file__).read_text(encoding="utf8")
    # ⚠ The editor's script lives inside an f-string, so every backslash in
    #   it is DOUBLED in the source. That is why this is matched on the
    #   doubled form: the browser sees the single one.
    assert r"/(?:^|;)\\s*Make:\\s*([^;\\n]+)/gi" in src, "the editor's regex moved"
    assert BQ._MAKE_IN_REMARK.pattern == r"(?:^|;)\s*Make:\s*([^;\n]+)"
    import re as _re
    assert BQ._MAKE_IN_REMARK.flags & _re.IGNORECASE


def test_make_prefill_skips_a_header_and_writes_no_empty_entry():
    lines = [
        {"line_id": "aaaaaaaaaaaa", "is_header": True, "remark": "Make: Jindal"},
        {"line_id": "bbbbbbbbbbbb", "is_header": False, "remark": "Make: KANEX"},
        {"line_id": "cccccccccccc", "is_header": False, "remark": "no brand"},
    ]
    out = BQ.make_prefill(lines)
    assert out == {"bbbbbbbbbbbb": "KANEX"}, (
        "a header carries the clause and no brand; a line with none is ABSENT "
        "rather than empty, so a caller can tell it from a cleared box")


# ═══ 2. Both pickers prefill ═══════════════════════════════════════════════

@pytest.fixture()
def shop(client):
    import address
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    STORE.setdefault("purchases", {}).clear()
    bid = next(b for b, rec in STORE["boqs"].items() if not rec.get("supersedes"))
    lines = [li for li in STORE["boqs"][bid]["line_items"]
             if not li.get("is_header")]
    lines[0]["remark"] = "Make: Jindal"
    lines[1]["remark"] = "an internal note with no brand"
    lines[2]["remark"] = "spec says; Make: KANEX"
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    yield {"boq": bid, "lines": lines, "vendor": vendor}
    STORE["purchase_orders"].clear()
    STORE["purchases"].clear()


@pytest.mark.parametrize("url", ["/purchase/from-boq/{boq}", "/po/create?boq={boq}"])
def test_both_pickers_prefill_from_the_remark(client, shop, url):
    html = client.get(url.format(boq=shop["boq"])).get_data(as_text=True)
    a, b, c = shop["lines"][0], shop["lines"][1], shop["lines"][2]
    assert f'id="m_{a["line_id"]}" value="Jindal"' in html
    assert f'id="m_{b["line_id"]}" value=""' in html
    assert f'id="m_{c["line_id"]}" value="KANEX"' in html
    assert html.count('data-prefill="1"') == 2, (
        "only a box that WAS prefilled says so")


@pytest.mark.parametrize("url", ["/purchase/from-boq/{boq}", "/po/create?boq={boq}"])
def test_a_prefilled_box_says_it_is_a_prefill_and_is_editable(client, shop, url):
    html = client.get(url.format(boq=shop["boq"])).get_data(as_text=True)
    cell = html.split(f'id="m_{shop["lines"][0]["line_id"]}"', 1)[1].split("/>", 1)[0]
    assert 'data-prefill="1"' in cell
    assert "import remark" in cell, "the box says where the value came from"
    assert "readonly" not in cell and "disabled" not in cell


def test_the_prefill_is_saved_onto_the_draft_po(client, shop):
    li = shop["lines"][0]
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": shop["vendor"], "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "make": "Jindal"}]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    d = next(iter(STORE["purchase_orders"].values()))
    row = next(x for x in d["items"] if not x.get("is_header"))
    assert row["make"] == "Jindal"
    assert '<td class="c-make">Jindal</td>' in client.get(
        f"/po/print/{d['id']}").get_data(as_text=True)


def test_clearing_a_prefilled_box_on_a_REFUSED_save_is_not_undone(client, shop):
    """
    ⚠ The one case presence-vs-truthiness decides. A rejected POST hands back
    an entry for every line the operator touched, including `""` for one they
    deliberately emptied — re-prefilling that from the schedule would put the
    value back after somebody removed it, which is the opposite of editable.
    """
    li = shop["lines"][0]
    # ⚠ No VENDOR is the refusal here, not a missing date: `_validate()` falls
    #   back to today when the date box is empty.
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": "", "vendor_name": "", "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "make": ""}]})})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert f'id="m_{li["line_id"]}" value=""' in html
    assert "Jindal" not in html.split(f'id="m_{li["line_id"]}"', 1)[1].split("/>", 1)[0]


def test_a_typed_make_on_a_refused_save_still_comes_back(client, shop):
    """The other half of the same branch — unchanged behaviour, re-asserted."""
    li = shop["lines"][1]            # the line with NO remark make
    r = client.post(f"/po/create?boq={shop['boq']}", data={
        "date": "2026-10-29", "vendor_id": "", "vendor_name": "", "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "4",
                                          "make": "SANT"}]})})
    assert r.status_code == 200
    assert f'id="m_{li["line_id"]}" value="SANT"' in r.get_data(as_text=True)


def test_the_prefill_writes_nothing_onto_the_boq(client, shop):
    """It is a form prefill and never a record. The schedule is not touched."""
    before = [dict(li) for li in STORE["boqs"][shop["boq"]]["line_items"]]
    client.get(f"/purchase/from-boq/{shop['boq']}")
    client.get(f"/po/create?boq={shop['boq']}")
    assert STORE["boqs"][shop["boq"]]["line_items"] == before
    for li in STORE["boqs"][shop["boq"]]["line_items"]:
        assert "make" not in li, "no make FIELD was added to a BOQ line"


def test_a_hostile_remark_cannot_inject_through_the_prefill(client, shop):
    shop["lines"][0]["remark"] = 'Make: "><script>alert(1)</script>'
    for url in (f"/purchase/from-boq/{shop['boq']}", f"/po/create?boq={shop['boq']}"):
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


def test_the_prefill_is_capped_at_the_make_column_width(client, shop):
    import boqpick as BP
    shop["lines"][0]["remark"] = "Make: " + "J" * 200
    html = client.get(f"/po/create?boq={shop['boq']}").get_data(as_text=True)
    cell = html.split(f'id="m_{shop["lines"][0]["line_id"]}"', 1)[1].split("/>", 1)[0]
    assert "J" * BP.MAKE_MAX in cell
    assert "J" * (BP.MAKE_MAX + 1) not in cell
