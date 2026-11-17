"""
A delivery challan WITHOUT a BOQ, and EXTRA items on any challan
(17 November 2026, CLIENT_CHANGES.md §0 seventy-fifth block).

What this file holds:

  * a no-BOQ challan is raised from `/dc/create?noboq=1`, with `boq_id` None,
    in the SAME number series, its lines being extra items only;
  * extra items ride on a BOQ challan after the BOQ lines, stored with
    `line_id` None and `extra` True, typed or picked from the specification
    library — which is never written;
  * an extra is never dispatched against a line and never billed: RA from DC
    skips it, a challan carrying only extras is not offered to an RA bill, and
    a no-BOQ challan is on no RA picker at all;
  * a no-BOQ challan with a `project_id` is listed on that project;
  * the printed challan keeps its three copy labels and carries no screen
    chip, and a challan with no extras prints byte-for-byte as before (the
    pinned golden in `test_print_golden.py` is the byte check; here the
    print of a legacy record is compared against itself through the new path).
"""

import copy

import pytest
from werkzeug.datastructures import MultiDict

import buypick as BYP
import challan
import docsheet as DS
import pipeline as P
import ra
import settings as SET
from store import STORE

from tests.test_challan import BID, _payload, boq_tip  # noqa: F401 — the fixture

CHIP = "Extra item, not billed"


def _form(**over):
    data = {"date": "2026-11-17", "dispatch_mode": "Transport",
            "dispatch_to": "Pune", "consignee_name": "Samruddhi Fire",
            "consignee_addr": "Site store", "consignee_phone": "",
            "po_no": "PO-77", "po_date": "2026-11-01", "notes": "",
            "xi_present": "1"}
    data.update(over)
    return data


def _extras(*rows):
    """`rows` = (desc, qty, unit[, pick]) → the repeater's posted lists."""
    md = []
    for r in rows:
        desc, qty, unit = r[0], r[1], r[2]
        pick = r[3] if len(r) > 3 else ""
        md += [("xi_desc", desc), ("xi_qty", qty), ("xi_unit", unit),
               ("line_product_id", pick)]
    return md


def _post(client, url, base, rows):
    return client.post(url, data=MultiDict(list(base.items()) + _extras(*rows)))


def r_ok(page):
    return "<form" in page


def _dcs():
    return STORE.setdefault("delivery_challans", {})


@pytest.fixture()
def clean(client):
    _dcs().clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)
    STORE.setdefault("projects", {}).pop("p-dc", None)
    yield client
    _dcs().clear()
    STORE["settings"].pop(SET.DC_SERIES_RECORD, None)
    STORE["projects"].pop("p-dc", None)


# ── A challan without a BOQ ─────────────────────────────────────────────────

def test_the_register_offers_new_dc_without_a_boq(clean):
    html = clean.get("/dc/").get_data(as_text=True)
    assert 'href="/dc/create?noboq=1"' in html and "New DC (no BOQ)" in html
    form = clean.get("/dc/create?noboq=1")
    assert form.status_code == 200
    page = form.get_data(as_text=True)
    assert "No BOQ" in page and 'name="xi_desc"' in page
    assert 'name="project_id"' in page and 'name="dc_json"' in page
    assert '<table class="pk-table">' not in page, "a no-BOQ challan draws no BOQ line picker"


def test_a_missing_boq_still_refuses_as_before(clean):
    r = clean.get("/dc/create")
    assert r.status_code == 302 and "/boq/" in r.headers["Location"]
    r = clean.get("/dc/create?boq=no-such-boq&noboq=1")
    assert r.status_code == 302 and "/boq/" in r.headers["Location"]


def test_a_no_boq_challan_is_raised_in_the_same_series(clean):
    SET.save_dc_series("", 54)
    r = _post(clean, "/dc/create?noboq=1", _form(),
              [("Pressure gauge 0-16 bar", "2", "Nos")])
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    dc = next(iter(_dcs().values()))
    assert dc["boq_id"] is None and dc["ref"] == "54"
    assert int(SET.dc_series()["next_no"]) == 55, "the same counter moved"
    assert dc["po_no"] == "PO-77" and dc["dispatch_to"] == "Pune"
    [row] = dc["items"]
    assert row["line_id"] is None and row["extra"] is True
    assert (row["description"], row["qty"], row["unit"]) == (
        "Pressure gauge 0-16 bar", 2.0, "Nos")
    # Register, view, print and delete all render with no BOQ behind it.
    reg = clean.get("/dc/").get_data(as_text=True)
    assert "No BOQ" in reg and "Open delivery challan 54" in reg
    view = clean.get(f"/dc/view/{dc['id']}").get_data(as_text=True)
    assert "Pressure gauge 0-16 bar" in view and CHIP in view
    assert "Raise RA" not in view
    assert clean.get(f"/dc/print/{dc['id']}").status_code == 200
    assert clean.get(f"/dc/edit/{dc['id']}").status_code == 200
    assert clean.get(f"/dc/delete/{dc['id']}").status_code == 200
    r = clean.post(f"/dc/delete/{dc['id']}")
    assert r.status_code == 302 and r.headers["Location"].startswith("/dc/")
    assert not _dcs()


@pytest.mark.parametrize("rows,needle", [
    ([], "nothing on it"),
    ([("Gauge", "0", "Nos")], "above 0"),
    ([("Gauge", "", "Nos")], "above 0"),
    ([("", "3", "Nos")], "no description"),
])
def test_a_no_boq_challan_refuses_a_bad_or_empty_item(clean, rows, needle):
    r = _post(clean, "/dc/create?noboq=1", _form(), rows)
    assert r.status_code == 200 and needle in r.get_data(as_text=True)
    assert not _dcs(), "nothing may be written"


def test_a_library_pick_fills_the_description_and_unit_and_writes_nothing(clean):
    BYP.ensure_seeded()
    entries = BYP.spec_entries()
    if not entries:
        pytest.skip("no specification library in this store")
    pick = entries[0]["value"]
    ident, _err = BYP.resolve(pick)
    before = copy.deepcopy(STORE.get("specs"))
    r = _post(clean, "/dc/create?noboq=1", _form(), [("", "4", "", pick)])
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    [row] = next(iter(_dcs().values()))["items"]
    assert row["description"] == ident["name"] and row["unit"] == ident["unit"]
    assert row["source"] == "spec" and row["line_id"] is None
    assert STORE.get("specs") == before, "the library was written to"


def test_a_project_link_is_snapshotted_and_listed_on_the_project(clean):
    STORE["projects"]["p-dc"] = {
        "id": "p-dc", "name": "Hinjewadi Warehouse", "norm_name":
        P.norm_name("Hinjewadi Warehouse"), "client": "X", "notes": "",
        "site_address_id": "", "site_address": "",
        "created_at": "2026-11-01 09:00", "updated_at": "2026-11-01 09:00"}
    SET.save_dc_series("", 300)
    r = _post(clean, "/dc/create?noboq=1", _form(project_id="p-dc"),
              [("Hose reel drum", "1", "Nos")])
    assert r.status_code == 302
    dc = next(iter(_dcs().values()))
    assert (dc["project_id"], dc["project_name"]) == ("p-dc", "Hinjewadi Warehouse")
    page = clean.get("/projects/view/p-dc").get_data(as_text=True)
    assert f'/dc/view/{dc["id"]}' in page and ">300<" in page
    # The register names the project from the snapshot.
    assert "Hinjewadi Warehouse" in clean.get("/dc/").get_data(as_text=True)


def test_an_unknown_project_is_refused(clean):
    r = _post(clean, "/dc/create?noboq=1", _form(project_id="gone"),
              [("Gauge", "1", "Nos")])
    assert r.status_code == 200 and "project no longer exists" in r.get_data(as_text=True)
    assert not _dcs()


# ── Extra items on a BOQ challan ────────────────────────────────────────────

def test_extras_ride_after_the_boq_lines_on_a_boq_challan(client, boq_tip):
    r = _post(client, f"/dc/create?boq={BID}",
              _form(dc_json=_payload(("bbbbbbbbbbbb", 3))),
              [("Spare gasket set", "5", "Set")])
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    dc = next(iter(_dcs().values()))
    assert [r.get("extra", False) for r in dc["items"] if not r["is_header"]] == [False, True]
    assert dc["items"][-1]["line_id"] is None
    html = client.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert html.index("80mm Butterfly valve") < html.index("Spare gasket set")
    assert CHIP not in html, "the screen chip reached paper"
    assert "<td class=\"c-sno\">2</td>" in html, "the extra takes the next Sr.No."
    # Dispatch against the schedule ignores the extra.
    assert challan.dispatched_by_line(BID) == {"bbbbbbbbbbbb": 3.0}


def test_a_boq_challan_may_carry_extras_only_and_is_never_unbilled(client, boq_tip):
    r = _post(client, f"/dc/create?boq={BID}", _form(dc_json=_payload()),
              [("Loose fittings", "1", "Lot")])
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    cid, dc = next(iter(_dcs().items()))
    assert not challan.has_boq_lines(dc)
    assert cid not in dict(ra.challans_on_chain(BID))
    view = client.get(f"/dc/view/{cid}").get_data(as_text=True)
    assert "Raise RA" not in view and CHIP in view


def test_ticking_nothing_and_adding_nothing_still_refuses(client, boq_tip):
    r = _post(client, f"/dc/create?boq={BID}", _form(dc_json=_payload()), [])
    assert r.status_code == 200 and "No lines are ticked" in r.get_data(as_text=True)
    assert not _dcs()


def test_ra_from_dc_skips_extras_and_never_sees_a_no_boq_challan(client, boq_tip):
    _post(client, f"/dc/create?boq={BID}",
          _form(dc_json=_payload(("cccccccccccc", 4))),
          [("Spare gasket set", "5", "Set")])
    _post(client, "/dc/create?noboq=1", _form(), [("Stray item", "9", "Nos")])
    boq_dc = next(d for d in _dcs().values() if d["boq_id"] == BID)
    lone = next(d for d in _dcs().values() if d["boq_id"] is None)
    assert ra.dispatched_in([boq_dc]) == {"cccccccccccc": 4.0}
    on_chain = dict(ra.challans_on_chain(BID))
    assert boq_dc["id"] in on_chain and lone["id"] not in on_chain
    page = client.get(f"/ra/create?boq={BID}&leg=supply").get_data(as_text=True)
    assert r_ok(page) and lone["id"] not in page and boq_dc["id"] in page
    picked, problems = ra.resolve_challans(BID, [lone["id"]])
    assert not picked and problems


def test_editing_keeps_extras_and_can_change_them(client, boq_tip):
    _post(client, f"/dc/create?boq={BID}",
          _form(dc_json=_payload(("bbbbbbbbbbbb", 2))),
          [("Spare gasket set", "5", "Set")])
    cid, dc = next(iter(_dcs().items()))
    page = client.get(f"/dc/edit/{cid}").get_data(as_text=True)
    assert 'value="Spare gasket set"' in page
    # A POST that does not carry the section leaves the extras alone.
    base = {k: v for k, v in _form().items() if k != "xi_present"}
    assert client.post(f"/dc/edit/{cid}", data=base).status_code == 302
    assert dc["items"][-1]["description"] == "Spare gasket set"
    # The form's own POST replaces them.
    r = _post(client, f"/dc/edit/{cid}",
              _form(dc_json=_payload(("bbbbbbbbbbbb", 2))),
              [("Spare gasket set", "6", "Set"), ("Teflon tape", "10", "Nos")])
    assert r.status_code == 302
    assert [(x["description"], x["qty"]) for x in dc["items"] if x.get("extra")] == [
        ("Spare gasket set", 6.0), ("Teflon tape", 10.0)]
    assert dc["items"][0]["line_id"] in ("aaaaaaaaaaaa", "bbbbbbbbbbbb")


# ── The printed challan ─────────────────────────────────────────────────────

def test_the_three_copy_labels_survive_on_a_no_boq_challan(clean):
    _post(clean, "/dc/create?noboq=1", _form(), [("Gauge", "1", "Nos")])
    dc = next(iter(_dcs().values()))
    html = clean.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    for label in DS.COPIES_DC:
        assert label in html, label
    assert html.count("DELIVERY CHALLAN") >= len(DS.COPIES_DC)
    assert "Name &amp; Signature of Receiver" in html
    assert CHIP not in html


def test_a_legacy_record_prints_exactly_as_before():
    """No new key on the record → the print path is the old one, byte for byte."""
    legacy = {"id": "x", "ref": "54", "date": "2026-07-28", "boq_id": "b",
              "boq_ref": "SF/BOQ/1", "consignee_name": "Samruddhi Fire",
              "items": [{"line_id": "aaaaaaaaaaaa", "is_header": False,
                         "item_no": "1", "description": "Valve", "unit": "Nos",
                         "qty": 2.0}]}
    assert challan._document_html(legacy) == challan._document_html(legacy, screen=True)
    assert CHIP not in challan._document_html(legacy, screen=True)
