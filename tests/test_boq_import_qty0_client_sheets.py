"""
The quantity-0 rule on the client's own sheets (7 October 2026,
CLIENT_CHANGES.md §0, forty-sixth block) — the real-sheet acceptance.

⚠ **These read the client's own files, which are gitignored** (`fixtures/`,
fixtures/README.md) and SKIP wherever they are absent. No cell of either sheet
is written into this file: every expectation is computed from the workbook at
run time, and every row left out is checked against the RAW CELLS of the grid
— not against the reader's own `price_figures`, so the two are held to each
other.

For each schedule tab, mapped as `tests/test_boq_as_is_client_sheets.py` maps
it (the column picker's advice, plus the Iron Mountain sheet's four cost
columns by hand):

* every row left out is a line whose quantity cell is the number 0 with no
  non-zero ticked rate or amount — or a heading or section the rule emptied;
* every line kept with a quantity cell of 0 carries a non-zero ticked rate or
  amount, or keeps a child;
* every rate-only "RO" line survives, byte for byte;
* the totals check, and the BOQ the form saves, do not move.
"""

import copy
import json

import pytest

import boqimport
import conftest
import sheetimport as SI
from store import STORE

SHEETS = [
    ("BOQ_Iron Mountain Rabale (1).xlsx", "Fire Fighting PR ",
     {"15": "supply_rate", "16": "supply_amount", "17": "install_rate",
      "18": "install_amount"}),
    ("Jamnagar Final updated.xlsx", "Quotation", {}),
]


def _number(value, kind):
    """The cell as a number when it is one — numeric, or text that reads as one
    — else None. A formula with no saved value is no number."""
    if kind == "formula" or value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    return float(s.replace(",", "")) if SI._NUMERIC_TEXT.match(s) else None


def _save(client, model, name):
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={"date": "2026-10-07", "project_name": name,
                                          "account_name": "", "boq_json": json.dumps(model)})
    assert r.status_code == 302, r.get_data(as_text=True)[:2000]
    (bid,) = set(STORE["boqs"]) - before
    return STORE["boqs"][bid]


@pytest.mark.parametrize("name,tab,extra", SHEETS, ids=[s[1].strip() for s in SHEETS])
def test_the_rule_on_the_client_sheet(client, name, tab, extra):
    path = conftest.require_fixture(name)
    wb = SI.read(path.read_bytes(), name)
    i = next(k for k, s in enumerate(wb["sheets"]) if s["name"] == tab)
    grid = wb["grid"][i]
    mapping = SI.clean_mapping(grid, {**SI.advised_mapping(grid), **extra})
    plain = SI.build(grid, mapping)
    res = boqimport.drop_qty0(copy.deepcopy(plain), tab.strip())

    ri_of = {rnum: ri for ri, (rnum, _vals) in enumerate(grid["rows"])}
    ci_of = {t: next(k for k, c in enumerate(grid["cols"]) if str(c) == col)
             for col, t in mapping.items() if t}

    def cell(row, target):
        ci = ci_of.get(target)
        if ci is None:
            return None
        ri = ri_of[row]
        return _number(SI._value(grid, ri, ci), SI._kind(grid, ri, ci))

    def priced_on_the_sheet(row):
        return any((cell(row, f) or 0) != 0 for f in SI.QTY0_PRICE_FIELDS if f in ci_of)

    left = {e["row"] for e in res.get("left_out") or []}
    by_row = {l["row"]: l for l in plain["lines"]}
    gone_secs = {s["code"] for s in res.get("left_out_sections") or []}
    kept_rows = {l["row"] for l in res["lines"]}

    # ── Every row left out is one the ruling names ─────────────────────────
    for row in left:
        l = by_row[row]
        assert row not in kept_rows
        if not l["is_header"]:
            if l["section"] in gone_secs and cell(row, "qty") != 0:
                continue                       # its section went, with it
            assert cell(row, "qty") == 0 and not l["rate_only"], (row, "the quantity cell is 0")
            assert not priced_on_the_sheet(row), (row, "no ticked rate or amount on the sheet")

    # ── Every line kept with a 0 in its quantity cell is priced, or a parent
    kids = {l.get("parent_item_no") for l in res["lines"] if l.get("parent_item_no")}
    for l in res["lines"]:
        if l["is_header"] or l["rate_only"] or cell(l["row"], "qty") != 0:
            continue
        assert priced_on_the_sheet(l["row"]) or l["item_no"] in kids, l["row"]

    # ── Every rate-only line survives, untouched ───────────────────────────
    ro_before = [l for l in plain["lines"] if l["rate_only"]]
    ro_after = [l for l in res["lines"] if l["rate_only"]]
    assert ro_after == ro_before

    # ── The totals check, and what the BOQ saves, do not move ─────────────
    assert res["totals"] == plain["totals"] and res["checks"] == plain["checks"]
    for c in res["totals"]["checks"]:
        if c.get("status") in ("match", "mismatch"):
            assert c["status"] == "match", c
    with_rule = _save(client, boqimport.editor_model(res), tab.strip())
    without = _save(client, boqimport.editor_model(plain), tab.strip() + " (all lines)")
    for k in ("supply_subtotal", "install_subtotal", "subtotal"):
        assert with_rule[k] == pytest.approx(without[k]), k
    assert len(with_rule["line_items"]) == len(without["line_items"]) - len(left)

    listed = ", ".join(f"row {e['row']} ({e['item_no'] or '-'})" for e in res.get("left_out") or [])
    print(f"\n{tab.strip()}: {len(left)} rows left out [{listed or 'none'}]; "
          f"{len(gone_secs)} sections went; {len(res.get('qty0_kept') or [])} kept for an amount; "
          f"{len(ro_after)} rate-only lines, all survived; "
          f"totals {res['totals']['status']}: "
          + "; ".join(f"{c['track']} {c['computed']:.2f} vs {c.get('sheet')}"
                      for c in res["totals"]["checks"]))
