"""
The delivery challan's TWO quantity columns, Qty (Mtr) and Qty (Nos)
(17 November 2026, CLIENT_CHANGES.md §0 eighty-second block, `dcqty.py`).

Their paper DC 63: Sr.No | Description | Qty (Mtr) | Qty (Nos) | Unit. A pipe
line carries both (482.4 Mtr, 80 nos); a fitting carries Nos only.

What this file holds:

  * both columns saved; one-column lines; at least one above 0;
  * the form's two boxes, prefilled by the line's unit, the other blank;
  * a line saved before this block renders by its unit — Mtr in the Mtr
    column, Nos/Pcs in the Nos column, anything else in the Nos column with
    its own unit in the Unit column;
  * billing counts the line's OWN unit: a 482.4 Mtr / 80 Nos pipe line counts
    482.4 against a Mtr BOQ line (dispatched, over-dispatch, RA-from-DC) and
    the PO remainder counts per unit;
  * the printed header carries both columns.
"""

import json
import re

import pytest
from werkzeug.datastructures import MultiDict

import challan
import dcpo
import dcqty as DQ
import ra
import settings as SET
from store import STORE

from tests.test_challan import _create, _doc, _line
from tests.test_dc_from_po import _form as _po_form, _keys, boq_po  # noqa: F401
from tests.test_boq_to_po import shop  # noqa: F401

BID = "dc2q-boq"
PIPE, VALVE, KG = "aaaaaaaaaaa1", "aaaaaaaaaaa2", "aaaaaaaaaaa3"


@pytest.fixture()
def sched(client):
    STORE.setdefault("delivery_challans", {}).clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)
    STORE["boqs"][BID] = {
        "id": BID, "ref": "SF/BOQ/26-27/0099", "fy": "26-27", "date": "2026-04-01",
        "rev_no": 0, "supersedes": "", "project_name": "Pipe site",
        "site_location": "Bangalore", "account_name": "Client", "to": "Client",
        "bill_gstin": "", "ship_same": "on",
        "sections": [{"code": "A", "title": "Hydrant", "areas": ["T1"]}],
        "line_items": [_line(PIPE, "1", "150mm dia ISI pipe", unit="Mtr", qty=500.0),
                       _line(VALVE, "2", "150mm butterfly valve", unit="Nos", qty=6.0),
                       _line(KG, "3", "MS supports", unit="Kg", qty=120.0)],
    }
    yield BID
    STORE["boqs"].pop(BID, None)
    STORE["delivery_challans"].clear()


def _two(*rows):
    """rows: (line_id, mtr, nos) — the payload the two-box grid posts."""
    return json.dumps({"lines": [{"line_id": lid, "qty_mtr": m, "qty_nos": n}
                                 for lid, m, n in rows]})


def _only():
    [dc] = STORE["delivery_challans"].values()
    return dc


def _row(dc, lid):
    return next(r for r in dc["items"] if r.get("line_id") == lid)


# ── The data ────────────────────────────────────────────────────────────────

def test_both_columns_are_saved_and_qty_is_the_lines_own_unit(client, sched):
    r = _create(client, sched, _two((PIPE, "482.4", "80"), (VALVE, "", "3")))
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    dc = _only()
    pipe, valve = _row(dc, PIPE), _row(dc, VALVE)
    assert (pipe["qty_mtr"], pipe["qty_nos"], pipe["qty"]) == (482.4, 80.0, 482.4)
    assert (valve["qty_mtr"], valve["qty_nos"], valve["qty"]) == (None, 3.0, 3.0)


def test_another_unit_carries_its_quantity_in_the_second_column(client, sched):
    assert _create(client, sched, _two((KG, "", "45"))).status_code == 302
    kg = _row(_only(), KG)
    assert (kg["qty_mtr"], kg["qty_nos"], kg["qty"]) == (None, 45.0, 45.0)
    assert DQ.cols(kg) == (None, 45.0, "Kg")


@pytest.mark.parametrize("mtr,nos", [("", ""), ("0", "0"), ("abc", ""), ("-1", "")])
def test_at_least_one_column_above_zero_and_numbers_only(client, sched, mtr, nos):
    r = _create(client, sched, _two((PIPE, mtr, nos)))
    assert r.status_code == 200 and STORE["delivery_challans"] == {}
    assert "Qty (Mtr)" in r.get_data(as_text=True)


def test_a_single_qty_post_is_placed_by_the_lines_unit(client, sched):
    """An older page (or Import from Excel) posts one `qty`."""
    payload = json.dumps({"lines": [{"line_id": PIPE, "qty": "12"},
                                    {"line_id": VALVE, "qty": "2"}]})
    assert _create(client, sched, payload).status_code == 302
    dc = _only()
    assert (_row(dc, PIPE)["qty_mtr"], _row(dc, PIPE)["qty_nos"]) == (12.0, None)
    assert (_row(dc, VALVE)["qty_mtr"], _row(dc, VALVE)["qty_nos"]) == (None, 2.0)


# ── The forms ───────────────────────────────────────────────────────────────

def test_the_form_prefills_the_column_of_the_lines_unit(client, sched):
    html = client.get(f"/dc/create?boq={sched}").get_data(as_text=True)
    assert re.search(rf'id="qm_{PIPE}" value="500"', html)
    assert re.search(rf'id="qn_{PIPE}" value=""', html)
    assert re.search(rf'id="qm_{VALVE}" value=""', html)
    assert re.search(rf'id="qn_{VALVE}" value="6"', html)
    assert re.search(rf'id="qn_{KG}" value="120"', html)
    assert "qty_mtr: (el('qm_' + lid)" in html and "qty_nos: (el('qn_' + lid)" in html
    # The extra-items rows carry both boxes too.
    assert 'name="xi_qty_mtr"' in html and 'name="xi_qty_nos"' in html


def test_the_edit_form_shows_both_saved_columns(client, sched):
    _create(client, sched, _two((PIPE, "482.4", "80")))
    dc = _only()
    html = client.get(f"/dc/edit/{dc['id']}").get_data(as_text=True)
    assert re.search(rf'id="qm_{PIPE}" value="482.4"', html)
    assert re.search(rf'id="qn_{PIPE}" value="80"', html)


def test_extras_take_two_columns_and_an_older_single_qty(client, sched):
    md = MultiDict([("date", "2026-11-17"), ("consignee_name", "Us"),
                    ("dc_json", _two((VALVE, "", "1"))),
                    ("xi_desc", "GI pipe offcut"), ("xi_unit", "Mtr"),
                    ("xi_qty_mtr", "6.5"), ("xi_qty_nos", "1"), ("line_product_id", "")])
    assert client.post(f"/dc/create?boq={sched}", data=md).status_code == 302
    x = next(r for r in _only()["items"] if r.get("extra"))
    assert (x["qty_mtr"], x["qty_nos"], x["qty"]) == (6.5, 1.0, 6.5)
    # Edit: the stored pair comes back in the two boxes.
    html = client.get(f"/dc/edit/{_only()['id']}").get_data(as_text=True)
    assert 'name="xi_qty_mtr" value="6.5"' in html and 'name="xi_qty_nos" value="1"' in html
    STORE["delivery_challans"].clear()
    md = MultiDict([("date", "2026-11-17"), ("consignee_name", "Us"),
                    ("dc_json", _two((VALVE, "", "1"))),
                    ("xi_desc", "Teflon tape"), ("xi_unit", "Nos"), ("xi_qty", "4"),
                    ("line_product_id", "")])
    assert client.post(f"/dc/create?boq={sched}", data=md).status_code == 302
    x = next(r for r in _only()["items"] if r.get("extra"))
    assert (x["qty_mtr"], x["qty_nos"], x["qty"]) == (None, 4.0, 4.0)


# ── Legacy lines render by their unit ───────────────────────────────────────

def test_a_line_from_before_renders_in_the_column_of_its_unit(client, sched):
    STORE["delivery_challans"]["old"] = {
        "id": "old", "ref": "OLD-1", "date": "2026-10-01", "boq_id": sched,
        "consignee_name": "Us", "items": [
            {"line_id": PIPE, "is_header": False, "description": "Pipe", "unit": "Mtrs", "qty": 30.0},
            {"line_id": VALVE, "is_header": False, "description": "Valve", "unit": "Pcs", "qty": 2.0},
            {"line_id": KG, "is_header": False, "description": "Supports", "unit": "Kg", "qty": 45.0}]}
    doc = _doc(client.get("/dc/print/old").get_data(as_text=True))
    heads = re.findall(r'<th class="(c-[a-z-]+)">([^<]*)</th>', doc)
    assert heads == [("c-sno", "Sr.No."), ("c-desc", "Description"),
                     ("c-qty", "Qty (Mtr)"), ("c-qty", "Qty (Nos)"), ("c-unit", "Unit")]
    cells = re.findall(r'<td class="c-qty">([^<]*)</td>\s*<td class="c-qty">([^<]*)</td>\s*'
                       r'<td class="c-unit">([^<]*)</td>', doc)
    assert cells[:3] == [("30", "", "Nos"), ("", "2", "Nos"), ("", "45", "Kg")]
    # Nothing was migrated.
    assert "qty_mtr" not in STORE["delivery_challans"]["old"]["items"][0]


def test_the_print_has_both_columns_and_blank_cells(client, sched):
    _create(client, sched, _two((PIPE, "482.4", "80"), (VALVE, "", "3")))
    doc = _doc(client.get(f"/dc/print/{_only()['id']}").get_data(as_text=True))
    cells = re.findall(r'<td class="c-qty">([^<]*)</td>\s*<td class="c-qty">([^<]*)</td>\s*'
                       r'<td class="c-unit">([^<]*)</td>', doc)
    assert cells[:2] == [("482.4", "80", "Nos"), ("", "3", "Nos")]


# ── Billing counts the line's own unit ──────────────────────────────────────

def test_a_pipe_dc_counts_482_4_against_a_mtr_boq_line(client, sched):
    _create(client, sched, _two((PIPE, "482.4", "80")))
    dc = _only()
    assert challan.dispatched_by_line(sched)[PIPE] == pytest.approx(482.4)
    assert ra.dispatched_in([dc])[PIPE] == pytest.approx(482.4), "RA-from-DC's cap"
    # 482.4 of 500 is not over; a second 20 Mtr / 2 Nos load is — by the Mtr.
    assert challan.over_dispatched(dc) == []
    _create(client, sched, _two((PIPE, "20", "2")))
    second = next(d for d in STORE["delivery_challans"].values() if d is not dc)
    [(_no, _d, total, approved)] = challan.over_dispatched(second)
    assert (total, approved) == (pytest.approx(502.4), 500.0)


def test_ra_from_the_pipe_dc_prefills_the_metres(client, sched):
    from conftest import chain_ready
    chain_ready(sched)                  # plants a challan of its own
    before = set(STORE["delivery_challans"])
    _create(client, sched, _two((PIPE, "482.4", "80")))
    [cid] = set(STORE["delivery_challans"]) - before
    dc = STORE["delivery_challans"][cid]
    html = client.get(f"/ra/create?boq={sched}&leg=supply&dc={dc['id']}").get_data(as_text=True)
    assert re.search(rf'id="q_{PIPE}"[^>]*value="482.4"|value="482.4"[^>]*id="q_{PIPE}"', html), \
        "the bill is raised on the Mtr figure, never the 80 Nos"


def test_the_po_remainder_counts_the_lines_own_unit(boq_po, client):
    po = boq_po["po"]
    k = _keys(po, "boq")[0]
    unit = next(r["unit"] for r in dcpo.lines_of(po) if r["key"] == k)
    own_is_mtr = DQ.unit_class(unit) == "mtr"
    md = list(_po_form().items())
    for r in dcpo.lines_of(po):
        md.append(("pl_key", r["key"]))
        if r["key"] == k:
            md += [("pl_qty_mtr", "4" if own_is_mtr else "99"),
                   ("pl_qty_nos", "99" if own_is_mtr else "4"), ("pl_on", k)]
        else:
            md += [("pl_qty_mtr", ""), ("pl_qty_nos", "")]
    r = client.post(f"/dc/create?po={po['id']}", data=MultiDict(md))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert dcpo.remaining_by_key(po)[k] == 6.0, "4 of 10 in the own unit; the 99 is never counted"
