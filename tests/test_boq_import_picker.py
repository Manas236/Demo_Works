"""
The BOQ import: the user CHOOSES the columns, escalation is optional, a
discount is a field, names come through, tabs are sections (6 October 2026).

CLIENT_CHANGES.md §0, forty-fourth block — Manas's rulings R1 to R6, no
charge. The client's words: there is no standard BOQ format; let the user
choose what to import, with the app advising what to take.

Every workbook here is BUILT IN MEMORY (`sheetimport.from_rows()`); no binary
is committed and no text from a client's real sheet appears in this file. The
one test that reads the client's own Sify workbook skips where it is absent.

The load-bearing rules, each with its tests below:

* R1 — `sheetimport.advise()` is pure and right per target; the tick and the
  dropdown arrive set to it; an UNTICKED column is never read or flagged; the
  work order gets the same picker in its own words;
* R2 — only description, quantity and a rate (or amount) are asked for, only
  for ticked columns; escalation and base are never compulsory, and a blank
  escalation with no base is stored ABSENT, never 0;
* R3 — `boq.net_rate()` is the one price of a line: rounding (an exact half
  pinned), totals at net, the RA claim at net, the purchase prefill at the
  BASE rate, the spec library untouched, Disc % / Net Rate printed only where
  a discount is, the editor's JavaScript agreeing with Python;
* R4 — names detected with where they came from, editable, matched to the
  address book; item text word for word;
* R5 — two tabs, two sections, their own totals and a combined one, the size
  limit applied to the whole.
"""

import json
import re
import shutil
import subprocess

import pytest

import boq
import boqimport
import conftest
import ra
import sheetimport as SI
import workorder as W
from store import STORE

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


# ═══ Helpers ═════════════════════════════════════════════════════════════════

def grid_of(rows, name="BOQ"):
    return SI.from_rows([(name, "visible", rows)])["grid"][0]


def stage(rows_by_tab, name="sheet.xlsx"):
    """Stage synthetic tabs for the suite's signed-in Owner. Call AFTER `client`."""
    wb = SI.from_rows([(t, "visible", rows) for t, rows in rows_by_tab])
    tok, known = boqimport.stage(wb, name, conftest.ensure_test_user()["id"])
    return tok, known


def rendered_form(html: str) -> dict:
    """
    The preview's own controls AS RENDERED — what a browser would post with
    nothing touched: each select's selected option, each ticked box, the tab
    ticks, the two names, the checked rate mode, the markup.
    """
    form = {"picker": "1", "tab": []}
    for name, opts in re.findall(r'<select name="(map_\d+_\d+)"[^>]*>(.*?)</select>', html, re.S):
        m = re.search(r'<option value="([^"]*)" selected>', opts)
        form[name] = m.group(1) if m else ""
    for name in re.findall(r'<input type="checkbox" name="(use_\d+_\d+)" value="1" checked', html):
        form[name] = "1"
    form["tab"] = re.findall(r'<input type="checkbox" name="tab" value="(\d+)" checked', html)
    for k in ("project_name", "account_name"):
        m = re.search(rf'id="{k}" name="{k}" maxlength="200"\s*value="([^"]*)"', html)
        form[k] = (m.group(1).replace("&amp;", "&").replace("&quot;", '"')
                   .replace("&#x27;", "'").replace("&lt;", "<").replace("&gt;", ">")) if m else ""
    m = re.search(r'name="rate_mode" value="(\w+)" id="rm-\w+"\s*checked', html)
    if m:
        form["rate_mode"] = m.group(1)
    return form


def model_of(html: str) -> dict:
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", html, re.S)
    assert m, "the page carries no editor model"
    return json.loads(m.group(1))


def confirm(client, tok, **changes):
    """GET the preview, post its controls as rendered (with `changes`) as a
    confirm, follow to the prefilled form. Returns (preview_html, response)."""
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    for k, v in changes.items():
        if v is None:
            form.pop(k, None)
        else:
            form[k] = v
    form.setdefault("action", "confirm")
    return html, client.post(f"/boq/import/{tok}", data=form)


def open_form(client, tok, **changes):
    _html, r = confirm(client, tok, **changes)
    assert r.status_code == 303, r.get_data(as_text=True)[:3000]
    page = client.get(r.headers["Location"])
    assert page.status_code == 200
    return page.get_data(as_text=True)


def save_model(client, model, **form):
    """POST a model to /boq/create the way the editor would, and return the
    saved record (or the refusal page's text)."""
    data = {"date": "2026-10-06", "project_name": "P", "account_name": "A",
            "boq_json": json.dumps(model)}
    data.update(form)
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data=data)
    new = set(STORE["boqs"]) - before
    if r.status_code == 302 and new:
        return STORE["boqs"][new.pop()]
    return r.get_data(as_text=True)


def a_line(**kw):
    li = {"line_id": "", "item_no": "1", "parent_item_no": "", "section": "A",
          "is_header": False, "description": "Pipe", "remark": "", "unit": "Mtr",
          "area_qty": {}, "total_qty": "10",
          "supply_base_rate": "", "supply_escalation_pct": "", "supply_rate": "100",
          "supply_hsn": "", "supply_gst_rate": "",
          "install_base_rate": "", "install_escalation_pct": "", "install_rate": "",
          "install_sac": "", "install_gst_rate": ""}
    li.update(kw)
    return li


def one_section(*lines):
    return {"sections": [{"code": "A", "title": "", "areas": []}], "lines": list(lines)}


# ═══ A. advise() — pure, one test per target and per skip ════════════════════

@pytest.mark.parametrize("head,samples,ctx,want", [
    ("Sr. No.", ["1"], {"guess": "item_no"}, "item_no"),
    ("Description", ["Pipe"], {"guess": "description"}, "description"),
    ("Total Qty", ["10"], {"guess": "qty"}, "qty"),
    ("Unit", ["Nos"], {"guess": "unit"}, "unit"),
    ("Make", ["Jindal"], {"guess": "make"}, "make"),
    ("Remarks", ["as per drawing"], {"guess": ""}, "remark"),
    ("Supply Rate", ["100"], {"guess": "supply_rate"}, "supply_rate"),
    ("Installation Rate", ["50"], {"guess": "install_rate"}, "install_rate"),
    ("Supply Base Rate", ["90"], {"guess": "supply_base_rate"}, "supply_base_rate"),
    ("Supply Esc %", ["15"], {"guess": "escalation_pct"}, "escalation_pct"),
    ("Disc %", ["10"], {"guess": "", "left_track": "supply"}, "supply_disc_pct"),
    ("Installation Discount", ["5"], {"guess": ""}, "install_disc_pct"),
    ("Net Rate", ["90"], {"guess": "?", "left_track": "supply", "net_has_disc": True},
     "supply_net_rate"),
    ("Supply Amount", ["1000"], {"guess": "supply_amount"}, "supply_amount"),
    ("Amount", ["1000"], {"guess": "amount"}, "amount"),
    ("Rate", ["100"], {"guess": "?", "lone_rate": True}, "supply_rate"),
])
def test_advise_takes_each_target(head, samples, ctx, want):
    target, reason = SI.advise(head, samples, ctx)
    assert target == want, (head, reason)
    assert reason in SI.ADVICE.values() and "Skip" not in reason


@pytest.mark.parametrize("head,samples,ctx,why", [
    ("Esc %", [], {"guess": "escalation_pct", "all_blank": True}, "esc_none"),
    ("Base Rate", [], {"guess": "supply_base_rate", "all_blank": True}, "base_none"),
    ("Cumulative Amount", ["5000"], {"guess": "amount"}, "running"),
    ("Qty up to date", ["4"], {"guess": "qty"}, "running"),
    ("HSN Code", ["7306"], {"guess": ""}, "tax"),
    ("GF Qty", ["4"], {"guess": ""}, "qty_split"),
    ("", [], {}, "empty"),
    ("Some Notes Column Nobody Uses", ["x"], {"guess": ""}, "remark"),
    ("Spare", ["x"], {"guess": ""}, "other"),
    ("Supply Amount", [], {"guess": "supply_amount", "all_blank": True}, "amount_none"),
])
def test_advise_skips_what_the_boq_does_not_take(head, samples, ctx, why):
    target, reason = SI.advise(head, samples, ctx)
    assert reason == SI.ADVICE[why], (head, target, reason)
    if why != "remark":
        assert target == ""


def test_the_advice_quotes_the_brief_word_for_word():
    """The four sentences the brief gave, each reached by its own column."""
    assert SI.advise("Supply Rate", ["100"], {"guess": "supply_rate"})[1] == \
        "Looks like your selling rate. Take it."
    assert SI.advise("Esc %", [], {"guess": "escalation_pct", "all_blank": True})[1] == \
        "No escalation in this sheet. Skip it; the unit rate stands on its own."
    assert SI.advise("Disc %", ["10"], {})[1] == "Looks like a discount %. Take it as Discount."
    assert SI.advise("Running Total", ["10"], {"guess": "amount"})[1] == \
        "Running total, not a line value. Skip it."


@pytest.mark.parametrize("head,samples", [
    ("Discount Amt", ["250"]), ("Disc (Rs)", ["40"]), ("Disc", ["2500"]),
    ("Discount value", ["12"]), ("Less", ["150.50"]),
])
def test_a_discount_in_rupees_is_advised_to_the_remark(head, samples):
    assert SI.advise(head, samples, {}) == (
        "remark", "Looks like a discount amount, not a %. Map it to Remark.")


def test_a_lone_rate_is_a_selling_rate_on_a_boq_and_a_choice_on_a_work_order():
    assert SI.advise("Rate", ["100"], {"guess": "?", "lone_rate": True})[0] == "supply_rate"
    assert SI.advise("Rate", ["100"], {"guess": "?", "lone_rate": True, "doc": "wo"})[0] == "?"
    assert SI.advise("Rate", ["100"], {"guess": "?", "lone_rate": False})[0] == "?"


def test_a_net_rate_with_no_discount_column_is_the_rate_or_nothing():
    assert SI.advise("Net Rate", ["90"], {"guess": "?"})[0] == "supply_rate"
    assert SI.advise("Net Rate", ["90"], {"guess": "?", "net_has_rate": True}) == (
        "", SI.ADVICE["net_skip"])


def test_advise_is_pure_and_deterministic():
    args = ("Supply Rate", ["100", "200"], {"guess": "supply_rate", "tracks": ["supply"]})
    ctx_copy = dict(args[2])
    first = SI.advise(*args)
    assert all(SI.advise(*args) == first for _ in range(5))
    assert args[2] == ctx_copy, "advise() must not touch its context"
    import inspect
    src = inspect.getsource(SI.advise)
    assert "STORE" not in src and "request" not in src and "flask" not in src.lower()


def test_guess_mapping_is_unchanged_and_still_leaves_a_lone_rate_undecided():
    """R1 narrows the 29 Sep ruling by making the target user-CHOSEN; the reader's
    own guess still makes no track guess — the advice is what pre-sets it."""
    g = grid_of([["Sr", "Description", "Qty", "Unit", "Rate", "Amount"],
                 ["1", "Pipe", 10, "Mtrs", 100, 1000]])
    assert SI.guess_mapping(g)["4"] == SI.UNDECIDED
    assert SI.advised_mapping(g)["4"] == "supply_rate"


# ═══ B. advise_mapping() over a whole sheet ═════════════════════════════════

def test_the_whole_sheet_is_advised_column_by_column():
    g = grid_of([["Sr", "Description", "Qty", "Unit", "Rate", "Disc %", "Net Rate",
                  "Amount", "Esc %", "Remarks", "Cumulative Amount"],
                 ["1", "Pipe", 10, "Mtr", 100, 10, 90, 900, None, "ok", 900],
                 ["2", "Valve", 2, "Nos", 50, None, 50, 100, None, "", 1000]])
    adv = SI.advise_mapping(g)
    assert {c: t for c, (t, _r) in adv.items()} == {
        "0": "item_no", "1": "description", "2": "qty", "3": "unit",
        "4": "supply_rate", "5": "supply_disc_pct", "6": "supply_net_rate",
        "7": "amount", "8": "", "9": "remark", "10": ""}
    assert adv["8"][1] == SI.ADVICE["esc_none"] and adv["10"][1] == SI.ADVICE["running"]


def test_a_target_advised_twice_keeps_the_first():
    g = grid_of([["Sr", "Description", "Qty", "Unit", "Supply Rate", "Remarks", "Notes"],
                 ["1", "Pipe", 1, "Nos", 5, "a", "b"]])
    adv = SI.advise_mapping(g)
    assert adv["5"][0] == "remark" and adv["6"] == ("", SI.ADVICE["dup"])


def test_untracked_rates_just_left_of_a_unit_rate_are_its_base_and_escalation():
    """The Sify sheet's shape: `Mohali Rates | Rate increased in % | Supply U/
    Rate`, then `Mohali rates | Installation U/ Rate` — none naming a track."""
    g = grid_of([["Sr", "Description", "Qty", "Unit", "Base Rates", "Rate up %",
                  "Supply U/ Rate", "Supply AMT", "Base rates", "Installation U/ Rate"],
                 ["1", "Pipe", 2, "Mtr", 100, 15, 115, 230, 40, 40]])
    adv = SI.advised_mapping(g)
    assert [adv[str(c)] for c in range(4, 10)] == [
        "supply_base_rate", "escalation_pct", "supply_rate", "supply_amount",
        "install_base_rate", "install_rate"]
    assert not SI.mapping_problems(g, adv)


# ═══ C. An unticked column is ignored completely ═════════════════════════════

JUNK = [["Sr", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount", "Remarks", "Disc %"],
        ["1", "Pipe", 10, "Mtr", 100, 1000, "#REF!", 250],
        ["2", "Valve", 2, "Nos", 50, 100, "see note", "NA"],
        [None, "GRAND TOTAL", None, None, None, 1100, None, None],
        [None, "Notes for the client", None, None, None, None, "a remark below", 999]]


def test_an_unticked_column_is_never_read_or_flagged_by_the_reader():
    g = grid_of(JUNK)
    m = SI.advised_mapping(g)
    m["6"] = m["7"] = ""                                 # Remarks and Disc % unticked
    res = SI.build(g, m)
    blob = json.dumps(res)
    assert "#REF!" not in blob and "see note" not in blob and "250" not in blob
    assert "a remark below" not in blob, "the below-grand note quoted an unticked column"
    (note,) = [f for f in res["flags"] if f["kind"] == "below_grand"]
    assert "Notes for the client" in note["message"], "the ticked column IS quoted"
    assert not [f for f in res["flags"] if f["col"] in ("G", "H")]
    assert all(l["remark"] == "" and l["supply_disc_pct"] is None for l in res["lines"])


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A1: a
#   discount of 250 is still not read as one, and it is now kept in the
#   remark (its note's kind is "as_remark"; it was "disc_range"). "NA" in a
#   discount is kept too.
#   The test as it stood:
#   def test_ticked_the_same_columns_are_read_and_flagged():
#       """The control for the test above."""
#       g = grid_of(JUNK)
#       m = SI.advised_mapping(g)
#       m["6"], m["7"] = "remark", "supply_disc_pct"
#       res = SI.build(g, m)
#       assert res["lines"][1]["remark"] == "see note"
#       assert any(f["kind"] == "disc_range" and f["row"] == 2 for f in res["flags"])

def test_ticked_the_same_columns_are_read_and_flagged():
    """The control for the test above."""
    g = grid_of(JUNK)
    m = SI.advised_mapping(g)
    m["6"], m["7"] = "remark", "supply_disc_pct"
    res = SI.build(g, m)
    assert res["lines"][1]["remark"] == "see note"
    assert any(f["kind"] == "as_remark" and f["row"] == 2 for f in res["flags"])
    assert res["lines"][0]["as_remark"] == ["Supply disc %: 250"]
    assert res["lines"][1]["as_remark"] == ["Supply disc %: NA"]


def test_an_unticked_column_never_reaches_the_form(client):
    tok, _k = stage([("BOQ", JUNK)])
    html = open_form(client, tok, use_0_6=None, use_0_7=None)
    model = model_of(html)
    assert all(l["remark"] == "" and l["supply_disc_pct"] == "" for l in model["lines"])
    assert "#REF!" not in json.dumps(model)


def test_a_dropdown_left_set_but_untick_is_still_ignored(client):
    """The tick governs, not the dropdown: an unticked column whose dropdown
    still says Remark is read for nothing."""
    tok, _k = stage([("BOQ", JUNK)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    assert form["map_0_6"] == "remark" and form.get("use_0_6") == "1"
    form.pop("use_0_6")
    form["action"] = "update"
    client.post(f"/boq/import/{tok}", data=form)
    assert STORE["boq_imports"][tok]["mapping"]["6"] == ""


def test_the_preview_lists_every_column_with_samples_a_tick_and_advice(client):
    tok, _k = stage([("BOQ", JUNK)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert html.count('name="map_0_') == 8 and html.count('name="use_0_') == 8
    assert "Pipe &middot; Valve" in html, "three sample values per column"
    assert SI.ADVICE["remark"] in html and SI.ADVICE["description"] in html
    assert "Only a <b>ticked</b> column is read" in html


# ═══ D. Only the minimum is required; escalation and base never are ═════════

NO_ESC = [["Sr", "Description", "Qty", "Unit", "Rate", "Esc %", "Amount"],
          ["1", "Pipe", 10, "Mtr", 100, None, 1000],
          ["2", "Valve", 2, "Nos", 50, None, 100]]


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: the
#   needs bar is gone, so its `data-count="0"` cannot be asserted; what is
#   held is that there is no bar and nothing is asked.
#   The test as it stood:
#   def test_a_sheet_with_no_escalation_imports_with_nothing_to_ask_and_saves(client):
#       tok, _k = stage([("BOQ", NO_ESC)])
#       assert STORE["boq_imports"][tok]["mapping"]["5"] == "", "empty escalation advised out"
#       html = open_form(client, tok)
#       model = model_of(html)
#       assert not any(l.get("_need") for l in model["lines"])
#       assert 'data-count="0"' in html, "the needs bar has nothing to count"
#       rec = save_model(client, model)
#       assert isinstance(rec, dict), rec[:500]
#       li = rec["line_items"][0]
#       assert li["supply_rate"] == 100.0 and li["supply_base_rate"] is None
#       assert li["supply_escalation_pct"] is None, "no base, no escalation: absent, never 0"
#       assert li["install_escalation_pct"] is None

def test_a_sheet_with_no_escalation_imports_with_nothing_to_ask_and_saves(client):
    tok, _k = stage([("BOQ", NO_ESC)])
    assert STORE["boq_imports"][tok]["mapping"]["5"] == "", "empty escalation advised out"
    html = open_form(client, tok)
    model = model_of(html)
    assert not any(l.get("_need") for l in model["lines"])
    assert 'id="needs-bar"' not in html, "there is no needs bar at all"
    rec = save_model(client, model)
    assert isinstance(rec, dict), rec[:500]
    li = rec["line_items"][0]
    assert li["supply_rate"] == 100.0 and li["supply_base_rate"] is None
    assert li["supply_escalation_pct"] is None, "no base, no escalation: absent, never 0"
    assert li["install_escalation_pct"] is None


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A1/A3:
#   a blank escalation beside a base rate is stored ABSENT, not 0.0 — the
#   forty-fourth block kept v1's "blank is 0" reading when a base was
#   present.
#   The test as it stood:
#   def test_base_given_and_escalation_blank_saves_with_the_typed_rate(client):
#       rec = save_model(client, one_section(a_line(supply_base_rate="100",
#                                                   supply_escalation_pct="",
#                                                   supply_rate="120")))
#       li = rec["line_items"][0]
#       assert (li["supply_base_rate"], li["supply_escalation_pct"], li["supply_rate"]) == (
#           100.0, 0.0, 120.0), "with a base the old reading stands; the typed rate stands"
#       assert li["supply_amount"] == 1200.0
#       assert "supply_disc_pct" not in li and "install_disc_pct" not in li, (
#           "no discount typed: the key is absent — never a 0 nobody wrote")

def test_base_given_and_escalation_blank_saves_with_the_typed_rate(client):
    rec = save_model(client, one_section(a_line(supply_base_rate="100",
                                                supply_escalation_pct="",
                                                supply_rate="120")))
    li = rec["line_items"][0]
    assert (li["supply_base_rate"], li["supply_escalation_pct"], li["supply_rate"]) == (
        100.0, None, 120.0), "a blank escalation is absent, base or no base; the rate stands"
    assert li["supply_amount"] == 1200.0
    assert "supply_disc_pct" not in li and "install_disc_pct" not in li, (
        "no discount typed: the key is absent — never a 0 nobody wrote")


def test_no_rate_column_ticked_asks_for_no_rate():
    g = grid_of([["Sr", "Description", "Qty", "Unit"], ["1", "Pipe", 10, "Mtr"]])
    res = SI.build(g, SI.advised_mapping(g))
    assert not res["needs"], "nothing ticked asks for a rate"
    m = SI.advised_mapping(grid_of([["Sr", "Description", "Qty", "Unit", "Supply Rate"],
                                    ["1", "Pipe", 10, "Mtr", None]]))
    assert m["4"] == "", "an empty rate column is advised out"


def test_a_base_rate_alone_prices_a_line():
    g = grid_of([["Sr", "Description", "Qty", "Unit", "Supply Base Rate", "Supply Esc %",
                  "Supply Rate"], ["1", "Pipe", 10, "Mtr", 100, 15, None]])
    res = SI.build(g, SI.guess_mapping(g))
    assert not [n for n in res["needs"] if n["field"] == "rate"]


def test_no_item_column_ticked_numbers_the_lines_itself():
    g = grid_of([["Description", "Qty", "Unit", "Supply Rate"],
                 ["Pipe", 10, "Mtr", 100], ["Valve", 2, "Nos", 50],
                 ["MS pipe, C class", None, None, None],
                 ["25 mm", 4, "Mtr", 10], ["32 mm", 3, "Mtr", 12]])
    res = SI.build(g, SI.advised_mapping(g))
    assert [(l["item_no"], l["item_src"]) for l in res["lines"]] == [
        ("1", "auto"), ("2", "auto"), ("3", "auto"), ("3.a", "auto"), ("3.b", "auto")]
    assert not res["needs"], "no Item No. column ticked: never asked for one"


def test_cost_mode_still_requires_the_markup(client):
    cost = [["Sr", "Description", "Qty", "Unit", "Own Cost Supply Rate", "Supply Amount"],
            ["1", "Pipe", 10, "Mtr", 100, 1000]]
    tok, _k = stage([("BOQ", cost)])
    _html, r = confirm(client, tok, rate_mode="cost", markup="")
    assert r.status_code == 200
    assert "Type the markup % for this cost sheet" in r.get_data(as_text=True)
    _html, r = confirm(client, tok, rate_mode="cost", markup="12")
    assert r.status_code == 303


@needs_node
def test_the_hint_never_asks_for_an_escalation_that_was_not_typed():
    """R2 in the editor: base 100, NO escalation, rate 120 — the rate stands
    and nothing says it "differs"; with an escalation typed, it still does."""
    from test_boq_import_guided import _DOM
    boot = one_section(a_line(supply_base_rate="100", supply_escalation_pct="",
                              supply_rate="120", _open=True),
                       a_line(item_no="2", supply_base_rate="100",
                              supply_escalation_pct="15", supply_rate="120", _open=True))
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = js.replace("BOQ_BOOT", json.dumps(boot)).replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}")
    script = ("var S = {}; var _g = document.getElementById;"
              "document.getElementById = function (id) { return STUB[id] || S[id] || (S[id] = new Elem(id)); };"
              "MODEL.sections[0]._open = true; renderLines(); hint(0); hint(1);"
              "console.log(JSON.stringify([S['sd0'].innerHTML, S['sd1'].innerHTML]));")
    out = subprocess.run([NODE], input=_DOM + js + "\n" + script, capture_output=True,
                         text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    no_esc, with_esc = json.loads(out.stdout.strip().splitlines()[-1])
    assert no_esc == "", "a base and no escalation: the typed rate stands, said nothing"
    assert "rate differs, kept as entered" in with_esc


# ═══ E. The discount and the net rate — the one helper ═══════════════════════

# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A8: the
#   net rate rounds HALF UP as Excel's ROUND does — 2.50 less 15% is 2.13 (it
#   was 2.12, half to even). Every other case is unchanged.
#   The test as it stood:
#   @pytest.mark.parametrize("unit,disc,net", [
#       (2.5, 15, 2.12),          # 2.125 exactly — half to EVEN (the house round())
#       (0.75, 50, 0.38),         # 0.375 exactly — half to even goes UP here
#       (2024.0, 10, 1821.6),
#       (100.0, 0, 100.0),        # a typed 0 is no arithmetic
#       (100.0, None, 100.0),     # absent
#       (7.000000000000001, None, 7.000000000000001),   # untouched, unrounded
#       (1999.99, 12.5, 1749.99),
#       (100.0, 100, 0.0),
#   ])
#   def test_net_rate_arithmetic(unit, disc, net):
#       assert boq.net_of(unit, disc) == net
#       line = {"supply_rate": unit, "install_rate": unit}
#       if disc is not None:
#           line["supply_disc_pct"] = line["install_disc_pct"] = disc
#       assert boq.net_rate(line, "supply") == net
#       assert boq.net_rate(line, "installation") == net, "ra.py's leg name is accepted"

@pytest.mark.parametrize("unit,disc,net", [
    (2.5, 15, 2.13),          # 2.125 exactly — half UP, Excel's ROUND (A8)
    (0.75, 50, 0.38),         # 0.375 exactly — up either way
    (2024.0, 10, 1821.6),
    (100.0, 0, 100.0),        # a typed 0 is no arithmetic
    (100.0, None, 100.0),     # absent
    (7.000000000000001, None, 7.000000000000001),   # untouched, unrounded
    (1999.99, 12.5, 1749.99),
    (100.0, 100, 0.0),
])
def test_net_rate_arithmetic(unit, disc, net):
    assert boq.net_of(unit, disc) == net
    line = {"supply_rate": unit, "install_rate": unit}
    if disc is not None:
        line["supply_disc_pct"] = line["install_disc_pct"] = disc
    assert boq.net_rate(line, "supply") == net
    assert boq.net_rate(line, "installation") == net, "ra.py's leg name is accepted"


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A8
#   reverses the forty-fourth block's half-to-even net rate by name: the
#   exact half is pinned at 2.13.
#   The test as it stood:
#   def test_the_exact_half_is_pinned():
#       """2.50 less 15% is EXACTLY 2.125 in binary: Python's round() takes it to
#       the even paisa, 2.12 — `purchase._line_total()`'s and the work order's
#       rule. A half-up rounding would print 2.13."""
#       assert 2.5 * (100 - 15) / 100 == 2.125
#       assert boq.net_of(2.5, 15) == 2.12

def test_the_exact_half_is_pinned():
    """2.50 less 15% is EXACTLY 2.125 in binary: Excel's ROUND — half up — takes
    it to 2.13, and so does the BOQ now (A8). Python's round() would give 2.12,
    the false "does not match the sheet" A8 was written to end."""
    assert 2.5 * (100 - 15) / 100 == 2.125
    assert boq.net_of(2.5, 15) == 2.13
    assert round(2.125, 2) == 2.12, "the house round() is unchanged everywhere else"


@pytest.mark.parametrize("raw,want", [
    ("", (None, False)), (None, (None, False)), ("-", (None, False)),
    ("10", (10.0, False)), ("10%", (10.0, False)), (" 12.5 % ", (12.5, False)),
    ("0", (0.0, False)), ("100", (100.0, False)),
    ("101", (None, True)), ("-1", (None, True)), ("ten", (None, True)), ("2,500", (None, True)),
])
def test_disc_value_reads_a_typed_discount(raw, want):
    assert boq.disc_value(raw) == want


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A8:
#   2.50 less 15% nets to 2.13 (half up), so the line and the subtotal move
#   by 0.01 × 2. The rest is unchanged.
#   The test as it stood:
#   def test_a_discounted_line_saves_at_net_and_the_totals_sum_net(client):
#       rec = save_model(client, one_section(
#           a_line(supply_rate="2024", supply_disc_pct="10", total_qty="3"),
#           a_line(item_no="2", supply_rate="2.5", supply_disc_pct="15", total_qty="2",
#                  install_rate="1000", install_disc_pct="5")))
#       a, b = rec["line_items"]
#       assert a["supply_rate"] == 2024.0 and a["supply_disc_pct"] == 10.0
#       assert a["supply_amount"] == pytest.approx(1821.6 * 3)
#       assert b["supply_amount"] == pytest.approx(2.12 * 2) and b["install_amount"] == 950.0 * 2
#       assert "install_disc_pct" not in a, "absent unless typed — never a 0 nobody wrote"
#       assert rec["supply_subtotal"] == pytest.approx(1821.6 * 3 + 2.12 * 2)
#       assert rec["subtotal"] == pytest.approx(rec["supply_subtotal"] + 1900.0)

def test_a_discounted_line_saves_at_net_and_the_totals_sum_net(client):
    rec = save_model(client, one_section(
        a_line(supply_rate="2024", supply_disc_pct="10", total_qty="3"),
        a_line(item_no="2", supply_rate="2.5", supply_disc_pct="15", total_qty="2",
               install_rate="1000", install_disc_pct="5")))
    a, b = rec["line_items"]
    assert a["supply_rate"] == 2024.0 and a["supply_disc_pct"] == 10.0
    assert a["supply_amount"] == pytest.approx(1821.6 * 3)
    assert b["supply_amount"] == pytest.approx(2.13 * 2) and b["install_amount"] == 950.0 * 2
    assert "install_disc_pct" not in a, "absent unless typed — never a 0 nobody wrote"
    assert rec["supply_subtotal"] == pytest.approx(1821.6 * 3 + 2.13 * 2)
    assert rec["subtotal"] == pytest.approx(rec["supply_subtotal"] + 1900.0)


def test_a_typed_zero_discount_is_kept_and_changes_nothing(client):
    rec = save_model(client, one_section(a_line(supply_disc_pct="0")))
    li = rec["line_items"][0]
    assert li["supply_disc_pct"] == 0.0 and li["supply_amount"] == 1000.0


@pytest.mark.parametrize("bad", ["101", "-5", "abc"])
def test_a_discount_that_is_no_percentage_is_refused_and_ringed(client, bad):
    body = save_model(client, one_section(a_line(supply_disc_pct=bad)))
    assert isinstance(body, str) and "a discount must be a % from 0 to 100" in body
    assert '"_err": ["supply_disc_pct"]' in body
    assert boq.line_problems(a_line(supply_disc_pct=bad), {"A": {"areas": []}}) == ["supply_disc_pct"]


@needs_node
def test_the_editor_prices_a_line_exactly_as_the_server_does():
    """`_BOQ_JS` `netRate()` / `round2()` / `discNum()` against `boq.net_of()`
    and `boq.disc_value()`, the exact halves included, and `errMet()` against
    `line_problems()` on the discount."""
    # ⚠ EXTENDED 6 October 2026 (the §0 forty-fifth block, A8): the half-up
    #   rule, and the halves binary cannot hold exactly — 10.05 less 50% is
    #   5.025, stored as 5.0249…, which Excel's ROUND (and now the BOQ) takes
    #   to 5.03. The list ended at (0.1, "30").
    cases = [(2.5, "15"), (0.75, "50"), (0.25, "50"), (5.25, "50"), (2024, "10"),
             (100.25, "10"), (1999.99, "12.5"), (7, "33.333"), (123.45, "7.5"),
             (100, ""), (100, "0"), (100, "10%"), (100, "100"), (0.1, "30"),
             (10.05, "50"), (1.15, "50"), (5.35, "50"), (99.99, "50"), (0.01, "50")]
    lines = [{"supply_rate": str(u), "supply_disc_pct": d} for u, d in cases]
    bad = ["", "-", "5", "5%", "101", "-1", "x", "1e3"]
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = js.replace("BOQ_BOOT", json.dumps({"sections": [], "lines": []}))
    js = js.replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}")
    stub = ("var STUB = {}; ['bulk-spec','bulk-section','line-editor','sec-editor','boq_json']"
            ".forEach(function(k){ STUB[k] = {value:'', innerHTML:''}; });\n"
            "var document = { getElementById: function(id) { return STUB[id] || null; } };\n")
    script = ("var L = " + json.dumps(lines) + "; var B = " + json.dumps(bad) + ";\n"
              "console.log(JSON.stringify({net: L.map(function (l) { return netRate(l, 'supply'); }),"
              " err: B.map(function (v) { return errMet({section: 'A', supply_disc_pct: v}, 'supply_disc_pct'); })}));")
    out = subprocess.run([NODE], input=stub + js + "\n" + script, capture_output=True,
                         text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["net"] == [boq.net_rate(l, "supply") for l in lines]
    assert got["err"] == [not boq.disc_value(v)[1] for v in bad]


@needs_node
def test_the_editor_writes_the_net_rate_and_amount_under_the_discount():
    from test_boq_import_guided import _DOM
    boot = one_section(a_line(supply_rate="2024", supply_disc_pct="10", total_qty="3",
                              _open=True))
    js = boq._BOQ_JS.replace("<script>", "").replace("</script>", "")
    js = js.replace("BOQ_BOOT", json.dumps(boot)).replace("BOQ_SPECS", "{}").replace("BOQ_ADDR", "{}")
    script = ("var S = {}; document.getElementById = function (id) { return STUB[id] || S[id] || (S[id] = new Elem(id)); };"
              "MODEL.sections[0]._open = true; renderLines(); netHint(0);"
              "var t = sectionTotals('A');"
              "console.log(JSON.stringify({hint: S['sn0'].innerHTML, total: t[0],"
              " cell: STUB['line-editor'].innerHTML.indexOf('aria-label=\"Supply discount %\"') !== -1}));")
    out = subprocess.run([NODE], input=_DOM + js + "\n" + script, capture_output=True,
                         text=True, timeout=30, encoding="utf8")
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["cell"], "a Disc % box on the line"
    assert "net <b>1,821.60</b>" in got["hint"] and "amount 5,464.80" in got["hint"]
    assert got["total"] == pytest.approx(5464.8), "the section bar sums at net"


# ═══ F. Every reader of the price ════════════════════════════════════════════

def _discounted_boq(bid="disc-boq"):
    line = {"line_id": "abcdefabcdef", "item_no": "1", "parent_item_no": "", "section": "A",
            "is_header": False, "description": "Pipe", "remark": "", "unit": "Mtr",
            "area_qty": {}, "total_qty": 10.0,
            "supply_base_rate": 1600.0, "supply_escalation_pct": 0.0, "supply_rate": 2024.0,
            "supply_disc_pct": 10.0, "supply_amount": 18216.0,
            "supply_hsn": "", "supply_gst_rate": 18.0,
            "install_base_rate": None, "install_escalation_pct": None, "install_rate": 500.0,
            "install_amount": 5000.0, "install_sac": "", "install_gst_rate": 18.0}
    STORE["boqs"][bid] = {"id": bid, "ref": "SF/BOQ/26-27/0901", "fy": "26-27",
                          "date": "2026-10-06", "rev_no": 0, "supersedes": "",
                          "project_id": "", "project_name": "P", "account_name": "A",
                          "sections": [{"code": "A", "title": "", "areas": []}],
                          "line_items": [line], "supply_subtotal": 18216.0,
                          "install_subtotal": 5000.0, "subtotal": 23216.0}
    return STORE["boqs"][bid], line


def test_the_ra_bill_is_priced_at_net(client):
    b, line = _discounted_boq()
    conftest.chain_ready(b["id"])
    rates = ra.approved_rates(b["id"])
    assert rates[("abcdefabcdef", "supply")] == 1821.6
    assert rates[("abcdefabcdef", "installation")] == 500.0
    html = client.get(f"/ra/create?boq={b['id']}&leg=supply").get_data(as_text=True)
    assert 'value="1821.6"' in html, "the claim grid is prefilled at the net rate"
    claims, err, _l = ra.clean_claims([{"line_id": "abcdefabcdef", "qty": "2",
                                        "rate": "1821.6"}], b, "supply", {})
    assert not err and claims[0]["approved_rate"] == 1821.6
    assert claims[0]["amount"] == 3643.2 and claims[0]["rate_varies"] is False


def test_an_issued_bill_does_not_move_when_a_discount_appears(client):
    """Existing RA bills are snapshots: a bill raised at the list rate keeps
    every figure after the schedule gains a discount."""
    b, line = _discounted_boq()
    line.pop("supply_disc_pct")
    c = ra.build_claim(line, 2, 2024.0, 0.0, ra.approved_rates(b["id"])[("abcdefabcdef", "supply")])
    assert c["approved_rate"] == 2024.0
    line["supply_disc_pct"] = 10.0                         # the revision's discount
    assert c["approved_rate"] == 2024.0 and c["amount"] == 4048.0


def test_the_purchase_prefill_stays_on_the_supply_base_rate(client):
    """Draft PO and purchase-from-BOQ: the COST side, where a discount given to
    the client does not apply."""
    import boqpick
    b, line = _discounted_boq()
    html = boqpick.rows_html(b, with_rate=True)
    assert 'value="1600.00"' in html and "1821.6" not in html
    items, err = boqpick.picked_lines(json.dumps({"lines": [{"line_id": "abcdefabcdef",
                                                              "qty": "2", "rate": ""}]}),
                                      b, empty_msg="none", cap_msg="cap", with_rate=True)
    assert not err and items[0]["rate"] == 1600.0, "a blank box falls back to the BASE rate"
    page = client.get(f"/purchase/from-boq/{b['id']}").get_data(as_text=True)
    assert 'value="1600.00"' in page


def test_the_spec_library_never_sees_a_discount(client):
    """No code path writes a BOQ line's rate into the library — the library
    only ever SUGGESTS a base rate into an empty box. Saving a discounted BOQ
    leaves every spec exactly as it was."""
    client.get("/boq/")
    before = json.dumps(STORE["specs"], sort_keys=True, default=str)
    rec = save_model(client, one_section(a_line(supply_rate="2024", supply_disc_pct="10")))
    assert isinstance(rec, dict)
    assert json.dumps(STORE["specs"], sort_keys=True, default=str) == before


# ═══ G. The import reads a discount, and checks it ═══════════════════════════

DISC_SHEET = [["Sr", "Description", "Qty", "Unit", "Supply Rate", "Disc %", "Net Rate",
               "Supply Amount"],
              ["1", "Pipe", 10, "Mtr", 100, 10, 90, 900],
              ["2", "Valve", 2, "Nos", 50, None, 50, 100],
              ["3", "Bend", 4, "Nos", 25, 20, 21, 80],          # net wrong by Rs 1.00 exactly
              ["4", "Tee", 3, "Nos", 40, 5, 38, 200]]           # amount wrong: 3 x 38 = 114


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A2: a
#   quantity × net rate that differs from the sheet's amount KEEPS the rate
#   and is an amber note on the line (it blanked the rate and was a need).
#   The test as it stood:
#   def test_the_discount_column_imports_and_both_checks_run():
#       g = grid_of(DISC_SHEET)
#       m = SI.advised_mapping(g)
#       assert (m["5"], m["6"]) == ("supply_disc_pct", "supply_net_rate")
#       res = SI.build(g, m)
#       by = {l["item_no"]: l for l in res["lines"]}
#       assert by["1"]["supply_disc_pct"] == 10.0 and not by["1"]["needs"]
#       assert by["2"]["supply_disc_pct"] is None and not by["2"]["needs"]
#       assert not by["3"]["needs"], "a net rate within a rupee agrees"
#       tee = by["4"]
#       assert tee["supply_rate"] is None, "the rate is left blank, never guessed"
#       msg = tee["needs"][0]["message"]
#       assert "net rate 38" in msg and "less 5%" in msg and "= 114" in msg and "200" in msg

def test_the_discount_column_imports_and_both_checks_run():
    g = grid_of(DISC_SHEET)
    m = SI.advised_mapping(g)
    assert (m["5"], m["6"]) == ("supply_disc_pct", "supply_net_rate")
    res = SI.build(g, m)
    by = {l["item_no"]: l for l in res["lines"]}
    assert by["1"]["supply_disc_pct"] == 10.0 and not by["1"]["flags"]
    assert by["2"]["supply_disc_pct"] is None and not by["2"]["flags"]
    assert not by["3"]["flags"], "a net rate within a rupee agrees"
    tee = by["4"]
    assert tee["supply_rate"] == 40.0, "the rate is the sheet's — never blanked"
    assert not res["needs"]
    (msg,) = tee["flags"]
    assert "the sheet says 200" in msg and "the BOQ computes 114" in msg
    assert "net rate 38" in msg


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A2: the
#   sheet's own net rate against rate less discount is an amber note that
#   keeps both (it blanked the rate and was a need).
#   The test as it stood:
#   def test_a_sheet_net_rate_off_by_more_than_a_rupee_is_flagged():
#       g = grid_of([DISC_SHEET[0], ["1", "Pipe", 10, "Mtr", 100, 10, 88.5, 885]])
#       res = SI.build(g, SI.advised_mapping(g))
#       (line,) = res["lines"]
#       assert line["supply_rate"] is None
#       assert "rate 100 less 10% = 90, but the sheet's net rate is 88.50" in line["needs"][0]["message"]

def test_a_sheet_net_rate_off_by_more_than_a_rupee_is_flagged():
    g = grid_of([DISC_SHEET[0], ["1", "Pipe", 10, "Mtr", 100, 10, 88.5, 885]])
    res = SI.build(g, SI.advised_mapping(g))
    (line,) = res["lines"]
    assert line["supply_rate"] == 100.0 and line["supply_disc_pct"] == 10.0
    assert not res["needs"]
    assert any("rate 100 less 10% is 90, the sheet's net rate is 88.50" in m
               for m in line["flags"])


def test_the_totals_check_sums_at_net():
    g = grid_of(DISC_SHEET[:3] + [[None, "Grand Total", None, None, None, None, None, 1000]])
    res = SI.build(g, SI.advised_mapping(g))
    assert res["totals"]["status"] == "match" and res["totals"]["checks"][0]["computed"] == 1000.0


def test_a_discount_amount_column_goes_to_the_remark_word_for_word(client):
    rows = [["Sr", "Description", "Qty", "Unit", "Supply Rate", "Discount Amt"],
            ["1", "Pipe", 10, "Mtr", 100, "Rs 250 on bulk"]]
    tok, _k = stage([("BOQ", rows)])
    assert STORE["boq_imports"][tok]["mapping"]["5"] == "remark"
    model = model_of(open_form(client, tok))
    assert model["lines"][0]["remark"] == "Rs 250 on bulk"
    assert model["lines"][0]["supply_disc_pct"] == ""


def test_the_discount_reaches_the_form_and_saves_at_net(client):
    tok, _k = stage([("BOQ", DISC_SHEET[:3])])
    model = model_of(open_form(client, tok))
    assert [l["supply_disc_pct"] for l in model["lines"]] == ["10", ""]
    rec = save_model(client, model)
    assert rec["line_items"][0]["supply_amount"] == 900.0 and rec["subtotal"] == 1000.0


# ═══ H. "Cost not recorded" ══════════════════════════════════════════════════

def test_the_project_page_says_cost_not_recorded_rather_than_showing_none(client, monkeypatch):
    monkeypatch.setitem(STORE["projects"], "pv-1", {"id": "pv-1", "name": "Job",
                                                    "site_address": "", "status": "active"})
    rec = save_model(client, one_section(a_line(), a_line(item_no="2", install_rate="50"),
                                         a_line(item_no="3", supply_base_rate="80")),
                     project_id="pv-1")
    assert boq.lines_without_cost(rec) == 2
    html = client.get("/projects/view/pv-1").get_data(as_text=True)
    assert "cost not recorded on 2 lines" in html
    for li in rec["line_items"]:
        li["supply_base_rate"] = 80.0
        li["install_base_rate"] = 40.0
    html = client.get("/projects/view/pv-1").get_data(as_text=True)
    assert "cost not recorded" not in html


def test_a_line_billed_on_no_track_needs_no_cost():
    rec = {"line_items": [dict(a_line(supply_rate=0.0), supply_rate=0.0, install_rate=0.0,
                               supply_base_rate=None, install_base_rate=None),
                          dict(a_line(), supply_rate=10.0, install_rate=0.0,
                               supply_base_rate=None, install_base_rate=None,
                               supply_disc_pct=100.0)]}
    assert boq.lines_without_cost(rec) == 0, "nothing billed: no cost to record"


# ═══ I. Names from the sheet ═════════════════════════════════════════════════

TITLED = [["BILL OF QUANTITIES"],
          ["Fire Fighting Works — Tower B"],
          ["Client :", "Acme Infra Pvt Ltd"],
          ["Sr", "Description", "Qty", "Unit", "Supply Rate"],
          ["1", "Pipe", 10, "Mtr", 100]]


def test_names_are_detected_with_where_they_came_from():
    names = SI.detect_names(grid_of(TITLED))
    assert names["project"] == {"text": "Fire Fighting Works — Tower B", "row": 2, "how": "title"}
    assert names["client"] == {"text": "Acme Infra Pvt Ltd", "row": 3, "how": "label"}


@pytest.mark.parametrize("rows,project,client_", [
    ([["Name of Work: Sprinklers at Plant 2"], ["M/s. Beta Constructions"]],
     "Sprinklers at Plant 2", "M/s. Beta Constructions"),
    ([["Project Name", "Kohinoor Phase II"], ["Customer - Gamma Ltd"]],
     "Kohinoor Phase II", "Gamma Ltd"),
    ([["BOQ"]], None, None),
])
def test_name_rows_of_several_shapes(rows, project, client_):
    names = SI.detect_names(grid_of(rows + [["Sr", "Description", "Qty", "Unit"],
                                            ["1", "x", 1, "Nos"]]))
    assert (names["project"] or {}).get("text") == project
    assert (names["client"] or {}).get("text") == client_


def test_the_preview_shows_each_name_and_its_source_and_they_are_editable(client):
    tok, _k = stage([("BOQ", TITLED)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert 'value="Fire Fighting Works — Tower B"' in html
    assert "From the sheet: tab “BOQ”, row 2." in html
    assert "From the sheet: tab “BOQ”, row 3." in html
    page = open_form(client, tok, project_name="Tower B Revised", account_name="Delta")
    assert 'value="Tower B Revised"' in page and 'value="Delta"' in page
    assert "Filled in from the sheet: the project name and the account name" in page


def test_nothing_found_falls_back_to_the_tab_name_and_says_so(client):
    tok, _k = stage([("Hydrant", [["Sr", "Description", "Qty", "Unit"], ["1", "x", 1, "Nos"]])])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert 'id="project_name" name="project_name" maxlength="200"\n                 value="Hydrant"' in html
    assert "the name of tab “Hydrant”" in html
    assert re.search(r'id="account_name" name="account_name" maxlength="200"\s*value=""', html)


def test_a_matching_address_book_entry_is_selected_on_the_form(client, monkeypatch):
    monkeypatch.setitem(STORE["addresses"], "adr-acme", {"id": "adr-acme", "label": "Acme (HO)", "type": "customer",
                                      "company": "ACME  Infra Pvt Ltd", "line1": "Plot 4",
                                      "line2": "MIDC", "city": "Pune", "state": "Maharashtra",
                                      "pincode": "411001", "gstin": "27AAACA1234A1Z5",
                                      "contact_name": "Mr K"})
    tok, _k = stage([("BOQ", TITLED)])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "Matches the address-book entry &ldquo;Acme (HO)&rdquo;" in html
    page = open_form(client, tok)
    assert '<option value="adr-acme" selected>' in page
    assert 'value="ACME  Infra Pvt Ltd"' in page and "Plot 4\nMIDC" in page
    assert 'value="27AAACA1234A1Z5"' in page and 'value="411001"' in page


def test_no_match_fills_the_free_text_and_selects_nothing(client):
    tok, _k = stage([("BOQ", TITLED)])
    page = open_form(client, tok)
    assert 'value="Acme Infra Pvt Ltd"' in page
    assert " selected>" not in page.split('id="bill_pick"')[1].split("</select>")[0]


def test_an_archived_entry_is_not_matched(monkeypatch):
    monkeypatch.setitem(STORE["addresses"], "adr-old", {"id": "adr-old", "label": "Old",
                                                        "company": "Zeta Ltd", "active": False})
    assert boqimport.address_match("Zeta Ltd") == (None, None)


# ═══ J. Item text word for word ══════════════════════════════════════════════

def test_item_descriptions_come_through_word_for_word(client):
    text = "  Supply of MS pipe  (C-Class)\nas per IS:1239 — Part 1, incl. FITTINGS  "
    tok, _k = stage([("BOQ", [["Sr", "Description", "Qty", "Unit", "Supply Rate"],
                              ["1", text, 2, "Mtr", 10]])])
    model = model_of(open_form(client, tok))
    assert model["lines"][0]["description"].strip() == text.strip()
    rec = save_model(client, model)
    assert rec["line_items"][0]["description"] == text.strip(), "only the ends trimmed"


# ═══ K. Several tabs, one BOQ — one tab per section ═══════════════════════════

TAB_A = [["Sr", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount"],
         ["1", "Pipe", 10, "Mtr", 100, 1000],
         ["2", "Valve", 2, "Nos", 50, 100],
         [None, "Total", None, None, None, 1100]]
TAB_B = [["Sr", "Description", "Qty", "Unit", "Supply Rate", "Supply Amount"],
         [None, "HYDRANT SYSTEM", None, None, None, None],
         ["1", "Hose", 3, "Nos", 200, 600],
         [None, "Total", None, None, None, 600]]


def test_two_tabs_build_into_two_sections_with_their_own_titles(client):
    tok, _k = stage([("Sprinkler", TAB_A), ("Hydrant", TAB_B)])
    _html, r = confirm(client, tok, action="update", tab=["0", "1"])
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert html.count("What each column holds") == 2
    assert "Sprinkler &mdash; Totals check (row 4, “Total”)" in html
    assert "Hydrant &mdash; Totals check (row 4, “Total”)" in html
    assert "Combined totals check, every ticked tab: Supply: " in html
    assert "matches</span> &#8377;&nbsp;1,700.00" in html, "the combined figure: 1,100 + 600"
    model = model_of(open_form(client, tok))
    assert [(s["code"], s["title"]) for s in model["sections"]] == [
        ("A", "Sprinkler"), ("B", "HYDRANT SYSTEM")]
    assert [(l["section"], l["item_no"]) for l in model["lines"]] == [
        ("A", "1"), ("A", "2"), ("B", "1")]
    rec = save_model(client, model)
    assert boq.section_totals(rec, "A") == (1100.0, 0.0)
    assert boq.section_totals(rec, "B") == (600.0, 0.0)


def test_a_tab_with_the_same_headers_takes_the_first_tabs_picks(client):
    tok, _k = stage([("One", TAB_A), ("Two", TAB_A)])
    rec = STORE["boq_imports"][tok]
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    form.pop("use_0_5")                                 # the user unticks the amount on tab 1
    form.update(tab=["0", "1"], action="update")
    client.post(f"/boq/import/{tok}", data=form)
    assert rec["tab_maps"]["1"] == rec["mapping"], "tab 2 copied tab 1's picks"
    assert rec["tab_maps"]["1"]["5"] == ""


# ⚠ AMENDED 6 October 2026 — CLIENT_CHANGES.md §0, forty-fifth block. A3: a
#   blank quantity no longer raises a need to carry the tab's name, so the
#   note that does is the sheet-vs-BOQ amount note on the line's `_flags`.
#   The test as it stood:
#   def test_a_flag_names_its_tab(client):
#       bad = [TAB_A[0], ["1", "Pipe", None, "Mtr", 100, 1000]]
#       tok, _k = stage([("Sprinkler", TAB_A), ("Hydrant", bad)])
#       confirm(client, tok, action="update", tab=["0", "1"])
#       model = model_of(open_form(client, tok))
#       msgs = [n["m"] for l in model["lines"] for n in (l.get("_need") or [])]
#       assert msgs and all(m.startswith("Hydrant · row 2:") for m in msgs)

def test_a_flag_names_its_tab(client):
    bad = [TAB_A[0], ["1", "Pipe", 2, "Mtr", 100, 999]]
    tok, _k = stage([("Sprinkler", TAB_A), ("Hydrant", bad)])
    confirm(client, tok, action="update", tab=["0", "1"])
    model = model_of(open_form(client, tok))
    msgs = [m for l in model["lines"] for m in (l.get("_flags") or [])]
    assert msgs and all(m.startswith("Hydrant · row 2:") for m in msgs)


def test_the_size_limit_applies_to_the_tabs_together(client, monkeypatch):
    """Each tab alone fits; together they do not — refused with the line
    count, never cut."""
    rows = [TAB_A[0]] + [[str(i), "x" * 40, 1, "Nos", 10, 10] for i in range(1, 41)]
    one = boqimport.too_large(boqimport.editor_model(SI.build(grid_of(rows),
                                                               SI.advised_mapping(grid_of(rows)))))
    assert one == ""
    size = len(json.dumps(boqimport.editor_model(SI.build(grid_of(rows), SI.advised_mapping(
        grid_of(rows)))), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    monkeypatch.setattr(boq, "MAX_JSON_BYTES", int(size * 1.5))
    tok, _k = stage([("One", rows), ("Two", rows)])
    _html, r = confirm(client, tok, tab=["0", "1"])
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "This sheet has 80 lines" in body
    assert STORE["boq_imports"][tok]["confirmed"] is False


def test_no_tab_ticked_is_refused(client):
    tok, _k = stage([("One", TAB_A)])
    _html, r = confirm(client, tok, tab=[])
    assert r.status_code == 200 and "Tick at least one tab to import." in r.get_data(as_text=True)


def test_one_tab_is_exactly_the_single_sheet_result():
    """R5 must not move a one-tab import by a byte."""
    g = grid_of(TAB_A)
    rec = {"grid": [g], "sheets": [{"name": "BOQ", "staged": True}], "sheet_index": 0,
           "mapping": SI.advised_mapping(g), "ticked": [0]}
    merged = boqimport.build_tabs(rec)
    plain = SI.build(g, SI.clean_mapping(g, SI.advised_mapping(g)))
    plain["tab_totals"] = []
    assert merged == plain


# ═══ L. The work order gets the same picker ═════════════════════════════════

def test_the_work_order_preview_is_the_same_picker_in_its_own_words(client):
    rows = [["Sr. No.", "Description", "Qty", "Unit", "Material Rate", "Labour Rate", "Remarks"],
            ["1", "Pipe laying", 10, "Mtr", 80, 20, "x"]]
    wb = SI.from_rows([("WO", "visible", rows)])
    tok = W.stage(wb, "wo.xlsx", conftest.ensure_test_user()["id"])
    html = client.get(f"/wo/import/{tok}").get_data(as_text=True)
    assert html.count('name="use_0_') == 7 and html.count('name="map_0_') == 7
    assert "Looks like the material rate. Take it." in html
    assert "Looks like the labour rate. Take it." in html
    assert "Not used on a work order. Skip it." in html, "a remark column has no WO field"
    assert W.advised_mapping(wb["grid"][0])["6"] == ""


def test_an_unticked_work_order_column_is_ignored(client):
    rows = [["Sr. No.", "Description", "Qty", "Unit", "Material Rate", "Labour Rate"],
            ["1", "Pipe laying", 10, "Mtr", 80, 20]]
    wb = SI.from_rows([("WO", "visible", rows)])
    tok = W.stage(wb, "wo.xlsx", conftest.ensure_test_user()["id"])
    html = client.get(f"/wo/import/{tok}").get_data(as_text=True)
    form = rendered_form(html)
    form.pop("use_0_4")                                  # untick the material rate
    form.update(tab=["0"], act="confirm")
    page = client.post(f"/wo/import/{tok}", data=form).get_data(as_text=True)
    assert '<option value="labour" selected>' in page, "only the labour track is left"
    assert 'name="ln_mrate"' not in page.split('<tbody id="wo-lines-body">')[1].split("</tbody>")[0], (
        "no material box on a line")


def test_a_lone_work_order_rate_is_still_a_choice():
    g = grid_of([["Sr. No.", "Description", "Qty", "Rate"], ["1", "Work", 1, 5]])
    assert W.advised_mapping(g)["3"] == SI.UNDECIDED


# ═══ M. The printed sheet ═══════════════════════════════════════════════════

def test_disc_and_net_columns_print_only_for_the_discounted_track(client):
    b, _line = _discounted_boq()
    html = client.get(f"/boq/print/{b['id']}").get_data(as_text=True)
    table = html[html.index('<table class="boq-table">'):]
    assert table.count("Disc %") == 1 and table.count("Net Rate") == 1, "supply only"
    assert "1,821.60" in table, "the net rate, printed"
    assert "Mohali" not in html and "1,600.00" not in table, "base rate still withheld"
    b["line_items"][0].pop("supply_disc_pct")
    html = client.get(f"/boq/print/{b['id']}").get_data(as_text=True)
    assert "Disc %" not in html and "Net Rate" not in html


def test_a_typed_zero_discount_prints_no_discount_columns(client):
    b, line = _discounted_boq()
    line["supply_disc_pct"] = 0.0
    assert not boq.any_discount(b, "supply")
    assert "Disc %" not in client.get(f"/boq/print/{b['id']}").get_data(as_text=True)


def test_every_row_of_a_discounted_sheet_fills_its_columns(client):
    """`tests/test_boq_print_columns.py`'s occupancy walk, on a discounted
    schedule with a header and both tracks discounted, view and print."""
    from test_boq_print_columns import _row_widths, _tables
    b, line = _discounted_boq()
    line["install_disc_pct"] = 5.0
    head = dict(line, line_id="aaaaaaaaaaab", item_no="H", is_header=True)
    b["line_items"].insert(0, head)
    b["sections"][0]["areas"] = ["L0"]
    line["area_qty"] = {"L0": 10.0}
    cols = {}
    for url in (f"/boq/print/{b['id']}", f"/boq/view/{b['id']}"):
        (t,) = _tables(client.get(url).get_data(as_text=True))
        assert set(_row_widths(t)) == {t["cols"]}, url
        cols[url.split("/")[2]] = t["cols"]
    # Print: Sr, Desc, L0, Qty, Unit, then per track rate + disc + net + amount.
    # The view adds each track's base rate (no escalation: none is carried).
    assert cols == {"print": 5 + 4 + 4, "view": 5 + 5 + 5}


# ═══ O. The client's own Sify workbook — skipped where it is absent ══════════

def test_the_default_advice_reads_the_sify_workbook_as_curated(sify_boq_xlsx):
    """
    The real-sheet check this pass could run: no new client sheet was placed
    in fixtures/ for it, but the Sify workbook is the client's own, and
    `tools/gen_demo_data.py` reads it with a hand-chosen mapping. The default
    advice, untouched, must choose THAT mapping, ask for nothing, and foot to
    the sheet's own grand total on both tracks.
    """
    st = SI.read(sify_boq_xlsx.read_bytes(), "sify_boq.xlsx")
    g = st["grid"][st["selected"]]
    m = SI.advised_mapping(g)
    taken = {c: t for c, t in m.items() if t and not t.endswith("_amount")}
    assert taken == {"0": "item_no", "1": "description", "4": "qty", "5": "unit",
                     "6": "supply_base_rate", "7": "escalation_pct", "8": "supply_rate",
                     "10": "install_base_rate", "11": "install_rate"}
    assert not SI.mapping_problems(g, m)
    res = SI.build(g, m)
    assert res["needs"] == [] and res["counts"]["lines"] == 87
    assert res["totals"]["status"] == "match"
    assert all(c["status"] == "match" for c in res["totals"]["checks"])
