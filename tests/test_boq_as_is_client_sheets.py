"""
The client's own workbooks open AS THEY ARE (6 October 2026, CLIENT_CHANGES.md
§0, forty-fifth block) — the real-sheet acceptance.

⚠ **These read the client's own files, which are gitignored** (`fixtures/`,
fixtures/README.md) and SKIP wherever they are absent. No cell of either sheet
is written into this file: every expectation is computed from the workbook at
run time.

For each schedule tab, with the column picker's advice (plus, on the Iron
Mountain sheet, the four cost columns its three-row heading hides, mapped by
hand exactly as ABOUT.md §5 `/boq/import` records the operator doing):

* the import asks for NOTHING — no need, no block, no ring, no bar;
* the BOQ SAVES as imported, untouched;
* cell by cell, for every mapped numeric column of every saved line: a blank
  cell is blank (`None`) on the record, a 0 is 0, a number is that number
  (a %-formatted cell as the % Excel shows), and text is blank with its words
  in the line's remark;
* the saved totals are the present amounts, and the sheet's own grand total is
  checked against them.
"""

import re
import json

import pytest

import boq
import boqimport
import conftest
import sheetimport as SI
from store import STORE

# (workbook, tab, columns mapped by hand on top of the advice)
SHEETS = [
    ("BOQ_Iron Mountain Rabale (1).xlsx", "Fire Fighting PR ",
     {"15": "supply_rate", "16": "supply_amount", "17": "install_rate",
      "18": "install_amount"}),
    ("Jamnagar Final updated.xlsx", "Quotation", {}),
]

# A mapped numeric target -> the key it is saved under.
SAVED_AS = {"qty": "total_qty", "supply_rate": "supply_rate", "install_rate": "install_rate",
            "supply_base_rate": "supply_base_rate", "escalation_pct": "supply_escalation_pct",
            "install_base_rate": "install_base_rate",
            "install_escalation_pct": "install_escalation_pct",
            "supply_disc_pct": "supply_disc_pct", "install_disc_pct": "install_disc_pct"}


def _expected(value, kind, field):
    """What the as-is rule says the saved figure is for one sheet cell, and the
    remark note it leaves (or "")."""
    if value is None or value == "" or kind == "formula":
        return None, ""
    if kind == "error":
        return None, f"{SI.REMARK_FIELD[field]}: {str(value).strip()} in sheet"
    if kind == "date":
        return None, f"{SI.REMARK_FIELD[field]}: {str(value).strip()}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        return (v * 100.0 if kind == "pct" and field in SI.PCT_FIELDS else v), ""
    s = str(value).strip()
    if SI._DASH.match(s):
        return None, ""
    t = s[:-1].strip() if field in SI.DISC_FIELDS and s.endswith("%") else s
    if SI._NUMERIC_TEXT.match(t):
        return float(t.replace(",", "")), ""
    return None, f"{SI.REMARK_FIELD[field]}: {s}"


@pytest.mark.parametrize("name,tab,extra", SHEETS, ids=[s[1].strip() for s in SHEETS])
def test_the_client_sheet_opens_and_saves_as_it_is(client, name, tab, extra):
    path = conftest.require_fixture(name)
    wb = SI.read(path.read_bytes(), name)
    i = next(k for k, s in enumerate(wb["sheets"]) if s["name"] == tab)
    grid = wb["grid"][i]
    mapping = SI.clean_mapping(grid, {**SI.advised_mapping(grid), **extra})
    res = SI.build(grid, mapping)

    # ── Nothing is asked for ────────────────────────────────────────────
    assert res["needs"] == [], "a blank is never a need"
    assert not any(l["block"] for l in res["lines"])
    model = boqimport.editor_model(res)
    assert not any("_need" in l or "_block" in l for l in model["lines"])

    # ── It saves, untouched ─────────────────────────────────────────────
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data={"date": "2026-10-06", "project_name": tab.strip(),
                                          "account_name": "", "boq_json": json.dumps(model)})
    assert r.status_code == 302, r.get_data(as_text=True)[:2000]
    (bid,) = set(STORE["boqs"]) - before
    saved = STORE["boqs"][bid]["line_items"]
    assert len(saved) == len(model["lines"])

    # ── Cell by cell ────────────────────────────────────────────────────
    ri_of = {rnum: ri for ri, (rnum, _vals) in enumerate(grid["rows"])}
    col_ci = {}
    for ci, c in enumerate(grid["cols"]):
        t = mapping.get(str(c), "")
        if t in SAVED_AS and t not in col_ci:
            col_ci[t] = ci
    checked = blanks = zeros = texts = 0
    for li, row in zip(saved, model["lines"]):
        if li["is_header"] or row.get("_ls"):
            continue
        ri = ri_of[row["_row"]]
        for field, ci in col_ci.items():
            if field == "qty" and row.get("_ro"):
                continue                       # "RO": quantity 0 by the 1 Oct ruling
            want, note = _expected(SI._value(grid, ri, ci), SI._kind(grid, ri, ci), field)
            got = li.get(SAVED_AS[field])
            if want is None:
                assert got is None, (row["_row"], field, got)
                blanks += 1
            else:
                assert got == pytest.approx(want), (row["_row"], field, got, want)
                zeros += want == 0
            if note:
                assert note in li["remark"], (row["_row"], field, li["remark"])
                texts += 1
            checked += 1
    assert checked > 0

    # ── The totals: present amounts only, and the sheet's own figure ────
    rec = STORE["boqs"][bid]
    sup = sum(l["supply_amount"] for l in saved if l.get("supply_amount") is not None)
    ins = sum(l["install_amount"] for l in saved if l.get("install_amount") is not None)
    assert rec["supply_subtotal"] == pytest.approx(sup)
    assert rec["install_subtotal"] == pytest.approx(ins)
    sheet = {c["track"]: c for c in res["totals"]["checks"]}
    report = {t: (round(c["computed"], 2), c.get("sheet"), c.get("status"))
              for t, c in sheet.items()}
    print(f"\n{tab.strip()}: {len(saved)} lines saved; {checked} mapped cells checked — "
          f"{blanks} blank, {zeros} zero, {texts} text kept in the remark; "
          f"totals vs the sheet: {res['totals']['status']} {report}; "
          f"BOQ supply {rec['supply_subtotal']:.2f}, installation {rec['install_subtotal']:.2f}; "
          f"lines with no amount: {boq.lines_without_amount(rec)}")
    for t, c in sheet.items():
        if c.get("status") in ("match", "mismatch"):
            assert c["status"] == "match", (t, c)

    # ── The page says nothing in red ────────────────────────────────────
    view = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    assert "need you" not in re.sub(r"<(script|style)>.*?</\1>", "", view, flags=re.S)
