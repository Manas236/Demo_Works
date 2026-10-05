"""
tests/test_work_orders.py — Work Orders for petty contractors (5 October 2026)
==============================================================================
CLIENT_CHANGES.md §0, forty-first block — Manas's rulings A to J. Each section
below is one ruling, or one property the brief named:

  A  its own collection, never inside a purchase order
  B  the print: the PO's sheet, title WORK ORDER, no GST — and a NEW golden
  C  lines: server-minted line_id, two rate tracks, amounts DERIVED
  D  Excel import through sheetimport.py — incl. the single-rate-column case
  E  DRAFT / ISSUED / CANCELLED, the RA bill's semantics; GET never mutates
  F  one global number, its own settings record, a deleted draft spends it
  G  the contractor: an address-book type with a typed fallback; GSTIN fill
  H  the optional project link, and the panel on /projects/view
  I  access: exactly the purchase order's, per action
  J  snapshot immutability — delete the address and the project; print unchanged

plus the escaping of every free-text field a work order carries.

PASS 3 (5 Oct 2026, the forty-third block) closes the file: R1 the tracks,
R4 sections, R5 GST (reversing B's "no GST"), R6 the site, R7 the terms, and
two new print goldens. The import half and the client's own sheet are
tests/test_wo_nxtra.py.
"""

import hashlib
import io
import re

import pytest

import auth
import db
import docsheet as DS
import settings as SET
import sheetimport as SI
import workorder as W
from store import STORE
from test_print_golden import (  # noqa: F401  (fixtures are used by pytest)
    SHEET_BLOCKS, _blocks, GOLD_PO, golden, pinned_identity,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _contractor(label="Ravi Fabricators", company="Ravi Fabricators Pvt Ltd",
                gstin="27AAAPZ1234C1ZV", aid=None) -> str:
    aid = aid or f"addr-con-{len(STORE['addresses'])}"
    STORE["addresses"][aid] = {
        "id": aid, "label": label, "type": "contractor",
        "contact_name": "Ravi", "company": company,
        "line1": "Shed 4, MIDC", "line2": "", "landmark": "",
        "city": "Pune", "state": "Maharashtra", "pincode": "411019",
        "country": "India", "phone": "", "email": "", "gstin": gstin,
    }
    return aid


def _project(name="Kohinoor Techpark", pid="proj-wo-1") -> str:
    STORE["projects"][pid] = {"id": pid, "name": name, "norm_name": name.lower(),
                              "client": "", "notes": "", "site_address_id": "",
                              "site_address": "", "created_at": "2026-10-01",
                              "updated_at": "2026-10-01"}
    return pid


def _lines(*rows):
    """Form fields for a list of (item, desc, unit, qty, mrate, lrate[, id])."""
    out = {k: [] for k in ("ln_id", "ln_item", "ln_desc", "ln_unit", "ln_qty",
                           "ln_mrate", "ln_lrate", "ln_note")}
    for r in rows:
        item, desc, unit, qty, m, l = r[:6]
        out["ln_id"].append(r[6] if len(r) > 6 else "")
        out["ln_item"].append(item)
        out["ln_desc"].append(desc)
        out["ln_unit"].append(unit)
        out["ln_qty"].append(qty)
        out["ln_mrate"].append(m)
        out["ln_lrate"].append(l)
        out["ln_note"].append("")
    return out


TWO_LINES = (("1", "Pipe laying, 50 NB", "m", "10", "100", "50.5"),
             ("2", "Painting, two coats", "sqm", "2.5", "0", "40"))


def _create(client, *rows, **over) -> str:
    data = {"date": "2026-10-05", "contractor_id": "", "contractor_name": "Ravi",
            "contractor_gstin": "", "contractor_addr": "Pune", "project_id": "",
            "notes": ""}
    data.update(_lines(*(rows or TWO_LINES)))
    data.update(over)
    before = set(STORE["work_orders"])
    r = client.post("/wo/create", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (wid,) = set(STORE["work_orders"]) - before
    return wid


@pytest.fixture(autouse=True)
def _clean_wo():
    STORE.setdefault("work_orders", {}).clear()
    W.staged().clear()
    saved = STORE["settings"].pop(SET.WO_SERIES_RECORD, None)
    yield
    STORE["work_orders"].clear()
    W.staged().clear()
    STORE["settings"].pop(SET.WO_SERIES_RECORD, None)
    if saved is not None:
        STORE["settings"][SET.WO_SERIES_RECORD] = saved
    for aid in [a for a in STORE["addresses"] if str(a).startswith("addr-con-")]:
        STORE["addresses"].pop(aid, None)
    STORE["projects"].pop("proj-wo-1", None)


# ══ A. Its own collection ════════════════════════════════════════════════════

def test_work_orders_is_its_own_persisted_collection(client):
    assert "work_orders" in db.COLLECTIONS and "work_orders" in db.LABELS
    purchases_before = dict(STORE["purchases"])
    drafts_before = dict(STORE.get("purchase_orders") or {})
    wid = _create(client)
    assert wid in STORE["work_orders"]
    assert STORE["purchases"] == purchases_before
    assert (STORE.get("purchase_orders") or {}) == drafts_before


def test_a_work_order_record_stores_a_gst_rate_but_no_tax_and_no_stored_amount(client):
    """
    Renamed 5 October 2026 (pass 3): R5 reverses ruling B's "no GST", so the
    record now carries a `gst_rate` (0 here — this POST sends none). The tax
    itself, like every amount, is derived and never stored.
    """
    wo = STORE["work_orders"][_create(client)]
    flat = repr(wo).lower()
    assert wo["gst_rate"] == 0.0 and wo["tracks"] == "both"
    for word in ("gst", "tax", "cgst", "sgst", "igst", "gst_amount"):
        assert word not in {k.lower() for k in wo}, word
    assert "contractor_gstin" in wo                     # the party's, not a tax
    for key in ("total", "grand_total", "subtotal", "material_total", "labour_total"):
        assert key not in wo
    for line in wo["lines"]:
        # `is_header` from 5 October 2026 (fix 2) — False on a priced line.
        assert set(line) == {"line_id", "is_header", "item_no", "description",
                             "unit", "qty", "material_rate", "labour_rate"}
        assert line["is_header"] is False
    assert "amount" not in flat


# ══ C. Lines: server-minted ids, both tracks, DERIVED amounts ═════════════════

def test_amounts_are_derived_per_line_and_rounded_once():
    line = {"qty": 3, "material_rate": 33.333, "labour_rate": 0.005}
    assert W.line_amounts(line) == (100.0, 0.01, 100.01)
    wo = {"lines": [line, {"qty": 2.5, "material_rate": 0, "labour_rate": 40}]}
    # `totals_of()` gained gst_rate / gst / total on 5 Oct 2026 (R5); the three
    # figures this test pins are unchanged.
    t = W.totals_of(wo)
    assert (t["material"], t["labour"], t["grand"]) == (100.0, 100.01, 200.01)
    assert (t["gst_rate"], t["gst"], t["total"]) == (0.0, 0.0, 200.01)   # no GST: absent


def test_both_rate_tracks_reach_the_print_in_their_own_columns(client):
    wid = _create(client)
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    cells = re.findall(r'<td class="c-(price|total)">([^<]*)</td>', html)
    # line 1: 10 x 100 material, 10 x 50.5 labour; line 2: 0 material, 2.5 x 40
    assert cells[:8] == [("price", "100.00"), ("total", "1,000.00"),
                         ("price", "50.50"), ("total", "505.00"),
                         ("price", "0.00"), ("total", "0.00"),
                         ("price", "40.00"), ("total", "100.00")]
    # Total row: material under material, labour under labour; then the grand.
    assert cells[8:] == [("price", ""), ("total", "1,000.00"), ("price", ""),
                         ("total", "605.00"), ("price", ""), ("total", ""),
                         ("price", ""), ("total", "1,605.00")]
    assert "One Thousand Six Hundred Five" in html


def test_a_changed_stored_rate_changes_the_printed_total_because_nothing_is_stored(client):
    wid = _create(client)
    STORE["work_orders"][wid]["lines"][0]["labour_rate"] = 60.0
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert ">1,700.00<" in html and ">1,605.00<" not in html   # 1,000 + (600 + 100)


def test_a_blank_rate_is_refused_and_never_read_as_zero(client):
    for field in ("ln_mrate", "ln_lrate"):
        data = {"date": "2026-10-05", "contractor_name": "Ravi"}
        data.update(_lines(("1", "Work", "m", "1", "5", "6")))
        data[field] = [""]
        html = client.post("/wo/create", data=data).get_data(as_text=True)
        assert not STORE["work_orders"]
        assert "type 0 if there is none" in html
        assert 'class="wo-need"' in html
    # …and a typed 0 is an answer.
    wid = _create(client, ("1", "Work", "m", "1", "0", "6"))
    assert STORE["work_orders"][wid]["lines"][0]["material_rate"] == 0.0


@pytest.mark.parametrize("field,value,fragment", [
    ("ln_desc", "", "needs a description"),
    ("ln_qty", "", "needs a quantity"),
    ("ln_qty", "-1", "cannot be negative"),
    ("ln_mrate", "abc", "is not a number"),
    ("ln_lrate", "1e12", "too large"),
])
def test_each_line_field_is_validated(client, field, value, fragment):
    data = {"date": "2026-10-05", "contractor_name": "Ravi"}
    data.update(_lines(("1", "Work", "m", "1", "5", "6")))
    data[field] = [value]
    html = client.post("/wo/create", data=data).get_data(as_text=True)
    assert fragment in html and not STORE["work_orders"]
    assert "Nothing was saved" in html


def test_a_work_order_with_no_line_is_refused(client):
    data = {"date": "2026-10-05", "contractor_name": "Ravi"}
    data.update(_lines(("", "", "", "", "", "")))
    html = client.post("/wo/create", data=data).get_data(as_text=True)
    assert "Add at least one line" in html and not STORE["work_orders"]


def test_line_ids_are_minted_by_the_server_never_taken_from_a_create(client):
    forged = "abcdefabcdef"
    wid = _create(client, ("1", "A", "m", "1", "1", "1", forged),
                  ("2", "B", "m", "1", "1", "1", forged))
    ids = [l["line_id"] for l in STORE["work_orders"][wid]["lines"]]
    assert forged not in ids and len(set(ids)) == 2
    assert all(re.fullmatch(r"[0-9a-f]{12}", i) for i in ids)


def test_edit_keeps_a_lines_id_and_mints_one_for_a_new_or_foreign_line(client):
    wid = _create(client)
    kept = STORE["work_orders"][wid]["lines"][0]["line_id"]
    dropped = STORE["work_orders"][wid]["lines"][1]["line_id"]
    data = {"date": "2026-10-06", "contractor_name": "Ravi"}
    data.update(_lines(("1", "Pipe laying, 50 NB", "m", "12", "100", "50.5", kept),
                       ("3", "New line", "nos", "1", "5", "5", ""),
                       ("4", "Forged", "nos", "1", "5", "5", "0123456789ab"),
                       ("5", "Copied", "nos", "1", "5", "5", kept)))
    assert client.post(f"/wo/edit/{wid}", data=data).status_code == 302
    lines = STORE["work_orders"][wid]["lines"]
    ids = [l["line_id"] for l in lines]
    assert ids[0] == kept                                  # kept verbatim
    assert dropped not in ids                              # deleted on the form
    assert "0123456789ab" not in ids                       # never trusted
    assert len(set(ids)) == 4                              # the copy re-minted
    assert lines[0]["qty"] == 12.0 and STORE["work_orders"][wid]["date"] == "2026-10-06"


def test_the_form_can_add_and_delete_lines_in_the_browser(client):
    html = client.get("/wo/create").get_data(as_text=True)
    assert '<template id="wo-row-tpl">' in html
    assert "woAdd()" in html and "wo-del" in html
    assert "confirm(" not in html


# ══ E. The lifecycle ══════════════════════════════════════════════════════════

def test_a_new_work_order_is_a_draft_and_prints_the_draft_overprint(client):
    wid = _create(client)
    assert STORE["work_orders"][wid]["status"] == "draft"
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert '<div class="lc-mark lc-draft">DRAFT</div>' in html


def test_issue_locks_the_work_order(client):
    wid = _create(client)
    r = client.post(f"/wo/issue/{wid}", data={"issued_on": "2026-10-07"})
    assert r.status_code == 302
    wo = STORE["work_orders"][wid]
    assert wo["status"] == "issued" and wo["issued_on"] == "2026-10-07"
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert "lc-mark" not in html.split("</style>")[-1]     # prints clean

    snapshot = repr(wo)
    for method in ("get", "post"):
        r = getattr(client, method)(f"/wo/edit/{wid}",
                                    data={"date": "2026-12-12", "contractor_name": "X",
                                          **_lines(("9", "Z", "m", "1", "1", "1"))})
        assert r.status_code == 302 and "cannot+be+edited" in r.headers["Location"]
    for method in ("get", "post"):
        r = getattr(client, method)(f"/wo/delete/{wid}")
        assert r.status_code == 302 and "cannot+be+deleted" in r.headers["Location"]
        r = getattr(client, method)(f"/wo/issue/{wid}")
        assert r.status_code == 302 and "already+been+issued" in r.headers["Location"]
    assert repr(STORE["work_orders"][wid]) == snapshot


def test_cancelling_needs_a_reason_and_keeps_every_figure(client):
    wid = _create(client)
    client.post(f"/wo/issue/{wid}", data={})
    before = [dict(l) for l in STORE["work_orders"][wid]["lines"]]
    html = client.post(f"/wo/cancel/{wid}", data={"cancel_reason": "  "}).get_data(as_text=True)
    assert STORE["work_orders"][wid]["status"] == "issued"
    assert "Say why this work order is being cancelled" in html

    r = client.post(f"/wo/cancel/{wid}", data={"cancel_reason": "Scope changed",
                                               "cancelled_on": "2026-10-09"})
    assert r.status_code == 302
    wo = STORE["work_orders"][wid]
    assert (wo["status"], wo["cancel_reason"], wo["cancelled_on"]) == (
        "cancelled", "Scope changed", "2026-10-09")
    assert wo["lines"] == before and wo["ref"] == "SF/WO/0001"
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert '<div class="lc-mark lc-cancelled">CANCELLED</div>' in html
    assert "cancelled on 2026-10-09 &mdash; Scope changed" in html
    assert "SF/WO/0001 is not reissued" in html


def test_a_cancelled_work_order_cannot_be_edited_cancelled_again_or_deleted(client):
    wid = _create(client)
    client.post(f"/wo/cancel/{wid}", data={"cancel_reason": "Not needed"})
    assert STORE["work_orders"][wid]["status"] == "cancelled"   # a draft may be cancelled
    snapshot = repr(STORE["work_orders"][wid])
    for url in (f"/wo/edit/{wid}", f"/wo/cancel/{wid}", f"/wo/delete/{wid}",
                f"/wo/issue/{wid}"):
        r = client.post(url, data={"cancel_reason": "again", "date": "2026-01-01",
                                   "contractor_name": "X"})
        assert r.status_code == 302 and "/wo/view/" in r.headers["Location"], url
    assert repr(STORE["work_orders"][wid]) == snapshot


def test_an_unrecognised_status_reads_as_issued_and_locks():
    for st in (None, "", "submitted", "DRAFTX"):
        wo = {"ref": "SF/WO/0009", "status": st}
        assert W.status_of(wo) == "issued"
        assert not W.can_edit(wo)[0] and not W.can_delete(wo)[0]
        assert W.can_cancel(wo)[0]
    assert W.status_of({"status": " Draft "}) == "draft"


@pytest.mark.parametrize("route", ["issue", "cancel", "delete"])
def test_a_get_on_a_lifecycle_route_changes_nothing(client, route):
    wid = _create(client)
    snapshot = repr(STORE["work_orders"][wid])
    r = client.get(f"/wo/{route}/{wid}")
    assert r.status_code == 200
    assert repr(STORE["work_orders"].get(wid)) == snapshot
    # The GET is a confirmation, not a refused POST: it says nothing about a
    # missing reason. (Caught the mutant that took the POST branch on a GET.)
    assert "Say why" not in r.get_data(as_text=True)


def test_a_draft_is_deleted_on_post(client):
    wid = _create(client)
    r = client.post(f"/wo/delete/{wid}")
    assert r.status_code == 302 and wid not in STORE["work_orders"]
    assert "not+reissued" in r.headers["Location"]


# ══ F. Numbering ══════════════════════════════════════════════════════════════

def test_the_series_is_global_and_a_deleted_draft_never_hands_its_number_back(client):
    pid = _project()
    a = _create(client)
    b = _create(client, contractor_name="Somebody else", project_id=pid)
    assert [STORE["work_orders"][x]["ref"] for x in (a, b)] == ["SF/WO/0001", "SF/WO/0002"]
    client.post(f"/wo/delete/{b}")
    c = _create(client)
    assert STORE["work_orders"][c]["ref"] == "SF/WO/0003"
    assert W.next_ref() == "SF/WO/0004"


def test_the_prefix_and_next_number_come_from_their_own_settings_record(client):
    SET.save_wo_series("KD/WO", "41")
    wid = _create(client)
    assert STORE["work_orders"][wid]["ref"] == "KD/WO/0041"
    assert SET.wo_series() == {"prefix": "KD/WO", "next_no": "42"}
    # Its own record, not a branding override: the identity and the amber
    # completeness dot never see it.
    assert SET.WO_SERIES_RECORD != SET.RECORD_ID
    assert not any(k.startswith("wo") for k, *_r in SET.ALL_FIELDS)


def test_a_number_typed_below_one_already_issued_is_skipped_never_reissued(client):
    a = _create(client)
    SET.save_wo_series("", "1")
    b = _create(client)
    assert STORE["work_orders"][a]["ref"] == "SF/WO/0001"
    assert STORE["work_orders"][b]["ref"] == "SF/WO/0002"


def test_the_settings_page_offers_and_validates_the_series(client):
    html = client.get("/settings/").get_data(as_text=True)
    assert "Work Order Series" in html and 'name="wo_prefix"' in html
    assert 'name="wo_next_no"' in html and "Prints as\n                SF/WO/0001" in html
    assert SET._validate_wo_series({"wo_next_no": "x1"})[1] == "Work order next number: digits only."
    assert SET._validate_wo_series({"wo_next_no": "0"})[1] == "Work order next number: must be 1 or more."
    assert SET._validate_wo_series({"wo_prefix": "P" * 33})[1].startswith("Work order prefix")
    assert SET.wo_ref_of({"prefix": "", "next_no": "12a"}) == "SF/WO/0001"


# ══ G. The contractor ═════════════════════════════════════════════════════════

def test_contractor_is_an_address_type_and_only_contractors_are_offered(client):
    import address
    address.ensure_demo_addresses()
    assert address.ADDRESS_TYPES["contractor"] == "Contractor"
    con = _contractor()
    html = client.get("/wo/create").get_data(as_text=True)
    picker = html[html.index('id="contractor_id"'):html.index("</select>", html.index('id="contractor_id"'))]
    assert f'value="{con}"' in picker
    vendor = next(a for a, r in STORE["addresses"].items() if r.get("type") == "vendor")
    assert f'value="{vendor}"' not in picker
    # A vendor posted as a contractor is refused.
    data = {"date": "2026-10-05", "contractor_id": vendor, **_lines(*TWO_LINES)}
    html = client.post("/wo/create", data=data).get_data(as_text=True)
    assert not STORE["work_orders"]
    # Fix 3 (c): the refusal names BOTH ways forward.
    assert "not as a Contractor" in html
    assert "one-off boxes below instead" in html and "no address-book entry" in html
    assert "add the address to the address book as type" in html


def test_a_picked_contractor_is_snapshotted_at_create(client):
    con = _contractor()
    wid = _create(client, contractor_id=con, contractor_name="")
    wo = STORE["work_orders"][wid]
    assert wo["contractor_id"] == con and wo["contractor_source"] == "book"
    assert wo["contractor_name"] == "Ravi Fabricators Pvt Ltd"
    assert wo["contractor_gstin"] == "27AAAPZ1234C1ZV"
    assert wo["to"].startswith("Ravi Fabricators") and "Pune" in wo["to"]


def test_a_typed_contractor_is_the_fallback(client):
    wid = _create(client, contractor_name="Local painter", contractor_gstin="27abcde1234f1z5",
                  contractor_addr="Wakad")
    wo = STORE["work_orders"][wid]
    assert (wo["contractor_id"], wo["contractor_source"]) == ("", "typed")
    assert wo["to"] == "Local painter\nWakad" and wo["contractor_gstin"] == "27ABCDE1234F1Z5"
    data = {"date": "2026-10-05", "contractor_name": "", **_lines(*TWO_LINES)}
    html = client.post("/wo/create", data=data).get_data(as_text=True)
    assert "type a one-off contractor" in html


def test_gstin_auto_fill_works_for_the_contractor_type(client):
    """The fresh cache entry stamps the record at save, exactly as for a vendor."""
    import address
    import test_gst_lookup as TG
    assert address.GST_NO_ADDRESS_FILL_TYPE != "contractor"
    address.ensure_demo_addresses()          # the route seeds; do it first
    TG.plant()
    aid = TG.new_address(client, gstin=TG.GOOD, type="contractor",
                         label="GST contractor")
    try:
        rec = STORE["addresses"][aid]
        assert rec["type"] == "contractor" and rec["gst_status"] == "Active"
        assert rec["gst_verified_at"]
        form = client.get("/address/add").get_data(as_text=True)
        assert '<option value="contractor"' in form
    finally:
        STORE["addresses"].pop(aid, None)


def test_the_address_guard_counts_a_work_order_as_a_reference(client):
    import address
    con = _contractor()
    wid = _create(client, contractor_id=con, contractor_name="")
    refs = address.references_of(con)
    assert [(r["collection"], r["id"]) for r in refs] == [("work_orders", wid)]
    client.post(f"/address/delete/{con}")
    assert con in STORE["addresses"]                    # refused while referenced


# ══ H. The project link ═══════════════════════════════════════════════════════

def test_the_project_is_optional_and_snapshotted(client):
    pid = _project()
    wid = _create(client, project_id=pid)
    wo = STORE["work_orders"][wid]
    assert (wo["project_id"], wo["project_name"]) == (pid, "Kohinoor Techpark")
    none = STORE["work_orders"][_create(client)]
    assert (none["project_id"], none["project_name"]) == ("", "")
    html = client.post("/wo/create", data={"date": "2026-10-05", "contractor_name": "R",
                                           "project_id": "gone", **_lines(*TWO_LINES)}).get_data(as_text=True)
    assert "That project no longer exists" in html


def test_the_project_page_lists_its_work_orders_and_adds_nothing_up(client):
    pid = _project()
    a = _create(client, project_id=pid)
    b = _create(client, project_id=pid)
    _create(client)                                       # on no project
    html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
    panel = html[html.index("<h2>Work Orders</h2>"):html.index("<!-- Charges Panel -->")]
    for wid in (a, b):
        assert STORE["work_orders"][wid]["ref"] in panel
    assert panel.count("<tr>") == 3                        # header + two rows
    assert "Total" not in panel and "3,210.00" not in panel


def test_a_project_with_no_work_order_draws_no_panel(client):
    pid = _project()
    html = client.get(f"/projects/view/{pid}").get_data(as_text=True)
    assert "<h2>Work Orders</h2>" not in html
    assert W.project_panel_html(pid) == "" and W.project_panel_html("") == ""


# ══ J. Snapshot immutability ══════════════════════════════════════════════════

def test_the_print_is_unchanged_when_the_address_and_the_project_go(client):
    con = _contractor()
    pid = _project()
    wid = _create(client, contractor_id=con, contractor_name="", project_id=pid)
    client.post(f"/wo/issue/{wid}", data={"issued_on": "2026-10-07"})
    before = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    # The address is EDITED, then removed outright (the route refuses while the
    # work order names it, so it goes from the store), and so does the project.
    STORE["addresses"][con].update(company="Renamed Ltd", city="Nagpur", gstin="")
    assert client.get(f"/wo/print/{wid}").get_data(as_text=True) == before
    STORE["addresses"].pop(con)
    STORE["projects"].pop(pid)
    after = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert after == before
    assert "Kohinoor Techpark" in after and "Ravi Fabricators Pvt Ltd" in after
    assert client.get(f"/wo/view/{wid}").status_code == 200


# ══ B. The print — the PO's sheet, and a NEW golden ═══════════════════════════

GOLD_WO = "gold-wo"


@pytest.fixture()
def golden_wo(client, pinned_identity):
    """A fixed, ISSUED work order — every value written here, nothing derived from today."""
    STORE["work_orders"][GOLD_WO] = {
        "id": GOLD_WO, "ref": "SF/WO/0001", "date": "2026-10-05",
        "status": "issued", "issued_on": "2026-10-06",
        "contractor_id": "", "contractor_name": "Ravi Fabricators Pvt Ltd",
        "contractor_source": "typed",
        "to": "Ravi Fabricators Pvt Ltd\nShed 4, MIDC Bhosari\nPune 411026",
        "contractor_gstin": "27AAAPZ1234C1ZV",
        "project_id": "proj-gold", "project_name": "Kohinoor Techpark",
        "notes": "Work to be completed within 30 days of issue.",
        "lines": [
            {"line_id": "aaaaaaaaaaa1", "item_no": "1", "unit": "Mtrs",
             "description": "Supply and laying of 50 NB MS pipe\nincluding clamps",
             "qty": 120.0, "material_rate": 410.0, "labour_rate": 95.5},
            {"line_id": "aaaaaaaaaaa2", "item_no": "1.a", "unit": "Nos",
             "description": "Sprinkler drop, pendent type",
             "qty": 36.0, "material_rate": 0.0, "labour_rate": 180.0},
            {"line_id": "aaaaaaaaaaa3", "item_no": "", "unit": "Sqm",
             "description": "Painting, two coats of synthetic enamel",
             "qty": 42.5, "material_rate": 65.25, "labour_rate": 0.0},
        ],
        "created_at": "2026-10-05 10:00", "created_by": "", "updated_at": "2026-10-05 10:00",
    }
    yield
    STORE["work_orders"].pop(GOLD_WO, None)


# Captured 5 October 2026 when the document was created — the first golden of
# a NEW print; it moved no other golden in tests/test_print_golden.py.
WO_WHOLE = "779dd2f7415cc6b4"
WO_LEN = 85375
WO_BLOCKS = {"head": "52d2340373bfc69c", "letterhead": "2800166c693cc2f1",
             "foot-strip": "1efaaf73d3a0a076", "doc-box": "a501572dc0470479",
             "party": "c1c123f5c20956ad", "items": "8ca1a53b005eba46",
             "signature": "66c13b84cc80040d"}


def test_the_work_order_print_matches_its_golden(client, golden_wo):
    html = client.get(f"/wo/print/{GOLD_WO}").get_data(as_text=True)
    got = (hashlib.sha256(html.encode("utf-8")).hexdigest()[:16], len(html))
    blocks = _blocks(html, SHEET_BLOCKS)
    assert got == (WO_WHOLE, WO_LEN), (
        f"the work order print changed: {got} against {(WO_WHOLE, WO_LEN)}; "
        f"blocks {blocks} against {WO_BLOCKS}")


def test_the_work_order_carries_the_purchase_orders_letterhead(client, golden, golden_wo):
    """Ruling B: the PO's sheet — so the letterhead and foot strip are its bytes."""
    po = _blocks(client.get(f"/purchase/view/{GOLD_PO}").get_data(as_text=True), SHEET_BLOCKS)
    wo = _blocks(client.get(f"/wo/print/{GOLD_WO}").get_data(as_text=True), SHEET_BLOCKS)
    assert wo["letterhead"] == po["letterhead"]
    assert wo["foot-strip"] == po["foot-strip"]
    assert wo["signature"] != ""


def test_the_work_order_print_is_the_document_the_ruling_describes(client, golden_wo):
    html = client.get(f"/wo/print/{GOLD_WO}").get_data(as_text=True)
    heads = re.findall(r'<th class="c-[a-z]+">([^<]*)</th>', html)
    assert heads == ["Sr", "Description", "Unit", "Qty", "Material Rate",
                     "Material Amount", "Labour Rate", "Labour Amount"]
    assert '<div class="doc-title">WORK ORDER</div>' in html
    assert "To (Contractor)" in html and "To (Supplier)" not in html
    for word in ("GST @", "CGST", "SGST", "IGST", "Taxable Value", "Bank Details"):
        assert word not in html, word
    assert "Work Order Value (in words) : INR" in html
    # Sr is the line's item number where it has one, its position where not.
    assert re.findall(r'<td class="c-sno">([^<]*)</td>', html) == ["1", "1.a", "3"]
    assert '<nav class="rail"' not in html and "no-print" in html
    assert "Grand Total (Material + Labour)" in html
    # 120 x 410 + 0 + 42.5 x 65.25 ; 120 x 95.5 + 36 x 180 + 0 = 17,940.00.
    # ⚠ 42.5 x 65.25 is EXACTLY 2,773.125 and prints 2,773.12: each line is
    #   `round(qty * rate, 2)`, `purchase._line_total()`'s house rule, which is
    #   Python's round-half-to-even on an exact binary half. Pinned, not chosen.
    assert ">2,773.12<" in html
    assert ">51,973.12<" in html and ">17,940.00<" in html and ">69,913.12<" in html


# ══ I. Access — exactly the purchase order's, per action ══════════════════════

PARITY = [
    ("workorder.list_wos",     "purchase.list_purchases"),
    ("workorder.view_wo",      "purchase.view_purchase"),
    ("workorder.print_wo",     "purchase.view_purchase"),
    ("workorder.create_wo",    "purchase.create_purchase"),
    ("workorder.import_wo",    "purchase.create_purchase"),
    ("workorder.import_preview", "purchase.create_purchase"),
    ("workorder.edit_wo",      "purchase.edit_purchase_rates"),
    ("workorder.issue_wo",     "purchase.update_purchase"),
    ("workorder.cancel_wo",    "purchase.update_purchase"),
    ("workorder.delete_wo",    "purchase.delete_purchase"),
]


def test_every_work_order_route_is_classified_and_mirrored_from_the_po():
    import app as app_module
    wo_eps = {r.endpoint for r in app_module.app.url_map.iter_rules()
              if r.endpoint.startswith("workorder.")}
    assert wo_eps == {w for w, _p in PARITY}
    for wo_ep, po_ep in PARITY:
        assert auth.ROUTE_PERMISSIONS[wo_ep] == auth.ROUTE_PERMISSIONS[po_ep], wo_ep
        assert (wo_ep in auth.OWNER_ONLY) == (po_ep in auth.OWNER_ONLY), wo_ep
    assert not [p for p in auth.PERMISSIONS
                if p.startswith(("wo.", "workorder.", "work_order"))]


@pytest.mark.parametrize("slug", ["owner", "director", "operation-head", "hr",
                                  "sales-manager", "purchase-manager", "accountant"])
def test_each_role_reaches_a_work_order_route_exactly_when_it_reaches_the_po_one(client, slug):
    auth.ensure_builtin_roles()
    name = f"wo-parity-{slug}"
    user = auth.find_user(name) or auth.create_user(
        name, name, f"{name}-password-123", [f"role-{slug}"], created_by="test")
    for wo_ep, po_ep in PARITY:
        assert auth.can_reach(wo_ep, user) == auth.can_reach(po_ep, user), (slug, wo_ep)


def test_the_gate_refuses_a_role_without_the_purchase_permissions(client):
    auth.ensure_builtin_roles()
    hr = auth.find_user("wo-gate-hr") or auth.create_user(
        "wo-gate-hr", "HR", "wo-gate-hr-password-1", ["role-hr"], created_by="test")
    assert not auth.can_reach("purchase.list_purchases", hr)
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = hr["id"]
    assert client.get("/wo/").status_code == 403
    assert client.get("/wo/create").status_code == 403


def test_delete_is_owner_only_exactly_as_the_pos(client):
    wid = _create(client)
    auth.ensure_builtin_roles()
    d = auth.find_user("wo-director") or auth.create_user(
        "wo-director", "Director", "wo-director-password-1", ["role-director"], created_by="test")
    assert "purchase.delete" in auth.permissions_of(d)
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = d["id"]
    for method in ("GET", "POST"):
        assert client.open(f"/wo/delete/{wid}", method=method).status_code == 403
        assert client.open("/purchase/delete/zz", method=method).status_code == 403
    assert wid in STORE["work_orders"]


# ══ The register, the dashboard card, the nav ═════════════════════════════════

def test_the_register_lists_each_work_order_with_its_derived_value(client):
    wid = _create(client)
    html = client.get("/wo/").get_data(as_text=True)
    assert "SF/WO/0001" in html and ">1,605.00<" in html
    assert f'href="/wo/view/{wid}"' in html


def test_the_dashboard_carries_a_work_orders_card_and_the_rail_does_not_yet(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/wo/"' in html
    rail = html[html.index('<nav class="rail"'):html.index("</nav>")]
    assert "/wo/" not in rail                               # queued, STATE.md
    card_at = html.index('href="/wo/"')
    assert card_at < html.index("<h2>Modules</h2>")         # outside the zones


def test_the_dashboard_card_is_not_drawn_for_a_role_that_cannot_open_it(client):
    auth.ensure_builtin_roles()
    hr = auth.find_user("wo-card-hr") or auth.create_user(
        "wo-card-hr", "HR", "wo-card-hr-password-1", ["role-hr"], created_by="test")
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = hr["id"]
    assert 'href="/wo/"' not in client.get("/").get_data(as_text=True)


def test_every_work_order_screen_page_carries_the_shell_and_the_print_does_not(client):
    wid = _create(client)
    for url in ("/wo/", "/wo/create", "/wo/import", f"/wo/view/{wid}",
                f"/wo/edit/{wid}", f"/wo/issue/{wid}", f"/wo/cancel/{wid}",
                f"/wo/delete/{wid}"):
        html = client.get(url).get_data(as_text=True)
        assert '<nav class="rail"' in html and '<div class="tb-name">Work Orders' in html, url
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert '<nav class="rail"' not in html and ".page-frame" in html


# ══ D. Excel import ═══════════════════════════════════════════════════════════

def _sheet(rows):
    return SI.from_rows([("WO", "visible", rows)])


def _confirm(client, wb, mapping=None, uid=None):
    from conftest import ensure_test_user
    tok = W.stage(wb, "contractor.xlsx", uid or ensure_test_user()["id"])
    sel = wb["selected"]
    grid = wb["grid"][sel]
    m = mapping if mapping is not None else W.guess_mapping(grid)
    # R4 (5 Oct 2026): the preview posts the ticked tabs and one mapping per
    # tab, named map_<tab>_<column>.
    data = {f"map_{sel}_{k}": v for k, v in m.items()}
    data["tab"] = [str(sel)]
    data["act"] = "confirm"
    return tok, client.post(f"/wo/import/{tok}", data=data)


def _priced(html, name):
    """The posted values of one column, PRICED rows only — a heading row posts
    hidden empty boxes too, so the lists stay aligned (R1/R4)."""
    out = []
    for tr in _body(html).split('<tr class="wo-ln')[1:]:
        if tr.startswith(" wo-hd"):
            continue
        out += re.findall(rf'name="{name}" value="([^"]*)"', tr)
    return out


def _body(html):
    """The form's line rows only — never the two <template> rows after them."""
    return html[html.index('<tbody id="wo-lines-body">'):html.index("</tbody>",
                html.index('<tbody id="wo-lines-body">'))]


def _values(html, name):
    """The posted values of one column of the form's rows, in order."""
    return re.findall(rf'name="{name}" value="([^"]*)"', _body(html))


ONE_RATE = [
    ["Sr. No.", "Description", "Unit", "Qty", "Material Rate", "Material Amount"],
    ["1", "Excavation", "cum", 10, 100, 1000],
    ["2", "Concrete", "cum", 3, 200, 600],
    [None, "Grand Total", None, None, None, 1600],
]


def test_a_sheet_with_one_rate_column_makes_a_one_track_work_order(client):
    """
    ⚠ AMENDED 5 October 2026 (the forty-third block, R1 — supersedes the
    per-line half of ruling D). It read `..._fills_that_track_and_leaves_the_
    other_blank_and_flagged` and asserted every line's labour rate blank and
    RINGED. A sheet with only a material column now imports as a MATERIAL ONLY
    work order — declared at the top of the form, changeable there — and the
    labour rate is neither drawn nor asked for. Still never guessed, never 0.
    """
    wb = _sheet(ONE_RATE)
    assert set(W.guess_mapping(wb["grid"][0]).values()) >= {"material_rate", "material_amount"}
    _tok, r = _confirm(client, wb)
    html = r.get_data(as_text=True)
    assert _priced(html, "ln_mrate") == ["100", "200"]
    assert 'name="ln_lrate"' not in html                         # not drawn at all
    assert 'class="wo-need"' not in _body(html)                  # nothing to answer
    assert '<option value="material" selected>' in html
    assert "this work order is Material only" in html
    assert not STORE["work_orders"]                              # nothing saved


def test_the_labour_only_sheet_is_the_mirror_case(client):
    rows = [["Sl", "Description", "Unit", "Qty", "Labour Rate"],
            ["1", "Fixing", "nos", 4, 25]]
    _tok, r = _confirm(client, _sheet(rows))
    html = r.get_data(as_text=True)
    assert _priced(html, "ln_lrate") == ["25"] and 'name="ln_mrate"' not in html
    assert '<option value="labour" selected>' in html


def test_both_tracks_import_and_the_reader_rules_carry_over(client):
    rows = [["Sr. No.", "Description", "Unit", "Qty", "Material Rate", "Labour Rate"],
            ["1", "Pipe work", None, None, None, None],
            ["1.1", "50 NB pipe", "m", 10, 400, 90],
            ["1.2", "Rate only line", "m", "R.O.", 300, 80],
            ["2", "Plaster", "sqm", 4, None, 30],
            ["3", "Painting", "sqm", 6, 20, 10]]
    _tok, r = _confirm(client, _sheet(rows))
    html = r.get_data(as_text=True)
    # ⚠ AMENDED 5 Oct 2026 (R4): a tab with no section title opens with its
    #   TAB NAME ("WO") as a section heading, so every list gains a first row.
    assert _values(html, "ln_item") == ["", "1", "1.1", "1.2", "2", "3"]
    assert _priced(html, "ln_qty") == ["10", "0", "4", "6"]
    assert _priced(html, "ln_mrate") == ["400", "300", "", "20"]
    assert _priced(html, "ln_lrate") == ["90", "80", "30", "10"]
    assert "rate only (RO) on the sheet" in html
    # Row 2 ("1  Pipe work") is a HEADING line (fix 2): no figure, nothing ringed.
    assert _values(html, "ln_hdr") == ["1", "1", "0", "0", "0", "0"]
    assert _values(html, "ln_sec") == ["1", "0", "0", "0", "0", "0"]
    head = _body(html).split('<tr class="wo-ln')[2]
    assert "wo-hd" in head and 'class="wo-need"' not in head
    assert "no material rate on this row" in html                 # row 2's blank


def test_a_rate_column_that_names_no_track_must_be_chosen(client):
    rows = [["Sr. No.", "Description", "Qty", "Rate"], ["1", "Work", 1, 5]]
    wb = _sheet(rows)
    tok, r = _confirm(client, wb)
    html = r.get_data(as_text=True)
    assert "does not say which: choose Material rate or Labour rate" in html
    assert not re.search(r'id="wo-form"', html)
    assert tok in W.staged()                                     # not consumed


def test_the_mapping_needs_a_description_and_a_quantity(client):
    wb = _sheet(ONE_RATE)
    grid = wb["grid"][0]
    m = {k: ("" if v in ("description", "qty") else v) for k, v in W.guess_mapping(grid).items()}
    probs = W.mapping_problems(grid, m)
    assert "Choose the column that holds the Description." in probs
    assert "Choose the column that holds the Quantity." in probs
    dup = dict(W.guess_mapping(grid))
    dup["2"] = "material_rate"
    assert any("Keep one" in p for p in W.mapping_problems(grid, dup))


def test_a_staged_import_belongs_to_its_uploader_and_is_consumed(client):
    auth.ensure_builtin_roles()
    other = auth.find_user("wo-import-other") or auth.create_user(
        "wo-import-other", "Other", "wo-import-other-password-1", ["role-owner"], created_by="test")
    tok = W.stage(_sheet(ONE_RATE), "x.xlsx", other["id"])
    r = client.get(f"/wo/import/{tok}")
    assert r.status_code == 302 and "expired+or+is+not+yours" in r.headers["Location"]
    tok2, r = _confirm(client, _sheet(ONE_RATE))
    assert r.status_code == 200 and tok2 not in W.staged()


def test_an_imported_sheet_saves_through_the_ordinary_form(client):
    """
    ⚠ AMENDED 5 October 2026 (R1, R4, R5). The sheet's one rate column makes a
    MATERIAL ONLY work order; posting a labour rate into it is now REFUSED
    (never silently dropped), and without one it saves. It used to demand a
    typed labour rate on every line. The tab-name section heading is posted
    back with the rest, exactly as rendered.
    """
    _tok, r = _confirm(client, _sheet(ONE_RATE))
    html = r.get_data(as_text=True)
    data = {"date": "2026-10-05", "contractor_name": "Ravi", "tracks": "material",
            "ln_id": _values(html, "ln_id"), "ln_note": _values(html, "ln_note"),
            "ln_hdr": _values(html, "ln_hdr"), "ln_sec": _values(html, "ln_sec"),
            "ln_item": _values(html, "ln_item"),
            "ln_desc": ["WO", "Excavation", "Concrete"],
            "ln_unit": _values(html, "ln_unit"), "ln_qty": _values(html, "ln_qty"),
            "ln_mrate": _values(html, "ln_mrate"), "ln_lrate": ["", "0", "15"]}
    html = client.post("/wo/create", data=data).get_data(as_text=True)
    assert not STORE["work_orders"]
    assert "Labour rates are typed on 2 lines (lines 2, 3) but this work order is Material only" in html
    del data["ln_lrate"]
    assert client.post("/wo/create", data=data).status_code == 302
    (wo,) = STORE["work_orders"].values()
    assert W.totals_of(wo)["material"] == 1600.0 and W.totals_of(wo)["labour"] == 0.0
    assert all("labour_rate" not in l for l in wo["lines"])     # absent, never 0


def test_a_real_workbook_goes_through_upload_preview_and_form(client):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in [["S.No", "Description of Work", "Unit", "Qty", "Material Rate",
                 "Labour Rate"], [1, "Core cutting", "nos", 12, 0, 350],
                [2, "Hanger supports", "nos", 40, 85, 30]]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/wo/import", data={"workbook": (io.BytesIO(buf.getvalue()), "wo.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 302 and "/wo/import/" in r.headers["Location"]
    tok = r.headers["Location"].rsplit("/", 1)[-1]
    html = client.get(f"/wo/import/{tok}").get_data(as_text=True)
    assert "wo.xlsx" in html and "Material rate" in html
    sel = W.staged()[tok]["sheet_index"]
    grid = W._grid(W.staged()[tok])
    data = {f"map_{sel}_{k}": v for k, v in W.guess_mapping(grid).items()}
    data.update(tab=[str(sel)], act="confirm")
    html = client.post(f"/wo/import/{tok}", data=data).get_data(as_text=True)
    assert _priced(html, "ln_mrate") == ["0", "85"] and _priced(html, "ln_lrate") == ["350", "30"]


def test_a_file_that_is_not_a_workbook_is_refused_in_words(client):
    r = client.post("/wo/import", data={"workbook": (io.BytesIO(b"not,a,workbook"), "x.csv")},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and not W.staged()
    assert "alert-error" in r.get_data(as_text=True)


# ══ Escaping — every free-text field a work order carries ═════════════════════

PAYLOAD = '<script>alert(1)</script>"\'&<img src=x onerror=alert(2)>'


def test_every_work_order_field_reaches_every_page_escaped(client):
    pid = _project(name="Proj " + PAYLOAD)
    wid = _create(client, ("I" + PAYLOAD[:20], "Desc " + PAYLOAD, "U" + PAYLOAD[:20],
                           "1", "1", "1"),
                  contractor_name="Con " + PAYLOAD, contractor_gstin="GST<b>",
                  contractor_addr="Addr " + PAYLOAD, notes="Notes " + PAYLOAD,
                  project_id=pid)
    wo = STORE["work_orders"][wid]
    pages = [f"/wo/view/{wid}", f"/wo/print/{wid}", "/wo/", f"/wo/edit/{wid}",
             f"/wo/issue/{wid}", f"/wo/cancel/{wid}", f"/wo/delete/{wid}",
             f"/projects/view/{pid}"]
    for url in pages:
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html, url
        assert "<img src=x onerror=alert(2)>" not in html, url
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html, url
    client.post(f"/wo/cancel/{wid}", data={"cancel_reason": "Why " + PAYLOAD})
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "Why &lt;script&gt;" in html
    assert wo["contractor_gstin"] == "GST<B>"


def test_an_imported_cell_and_file_name_are_escaped(client):
    rows = [["Sr. No.", "Description", "Qty", "Material Rate"],
            ["1", "Cell " + PAYLOAD, 1, 5]]
    from conftest import ensure_test_user
    tok = W.stage(_sheet(rows), "f" + PAYLOAD + ".xlsx", ensure_test_user()["id"])
    for html in (client.get(f"/wo/import/{tok}").get_data(as_text=True),
                 _confirm(client, _sheet(rows))[1].get_data(as_text=True)):
        assert "<script>alert(1)</script>" not in html
        assert "<img src=x onerror=alert(2)>" not in html


# ══ The leaf move — byte-identity of the RA sheet ════════════════════════════

def test_the_ra_stylesheet_is_byte_identical_after_the_overprint_moved_to_the_leaf():
    """
    `docsheet.LIFECYCLE_CSS` was cut out of `ra.RA_DOC_STYLES` and spliced
    back at the same character position. The digest is the one measured on the
    constant BEFORE the move (5 October 2026), so this fails on any byte.
    """
    import ra
    s = ra.RA_DOC_STYLES
    assert (len(s), hashlib.sha256(s.encode("utf-8")).hexdigest()) == (
        2185, "5388c565702b6983d119fbee22f4f2e61c6433d3d760fc521dee234ec0003ae2")
    assert DS.LIFECYCLE_CSS in s and DS.LIFECYCLE_CSS in W.WO_DOC_STYLES


# ══ Persistence — the snapshot-and-diff layer carries the new collection ══════

from test_persistence_isolation import a_store, fake_db  # noqa: E402,F401


def test_a_work_order_persists_and_fails_alone_in_words(fake_db):
    """`work_orders` is written like every other collection, isolated like one,
    and named to a human in words when it alone cannot be saved."""
    fake_db.refuse = {"work_orders"}
    result = db.sync(a_store())
    assert result["failed"] == ["work_orders"]
    assert result["written"] == len(db.COLLECTIONS) - 1
    assert db.failure_note() == ("Work orders are not being saved. "
                                 "Everything else is saving normally.")
    fake_db.refuse = set()
    assert db.sync(a_store())["failed"] == []
    assert fake_db.rows["work_orders"]


def test_a_stored_work_order_round_trips_through_the_json_blob(client):
    import json
    wo = STORE["work_orders"][_create(client)]
    back = json.loads(db._blob(wo))
    assert back == wo


# ══ FIX 1 (5 Oct 2026) — the import is staged by the BOQ importer's mechanism ═

def _xlsx(rows) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_staging_is_the_boq_mechanism_in_a_persisted_collection_of_its_own():
    import boqimport
    import importstage as IS
    assert not hasattr(W, "_STAGED")                     # no module-level cache
    assert "wo_imports" in db.COLLECTIONS and "wo_imports" in db.LABELS
    assert "boq_imports" in db.COLLECTIONS               # each importer its own
    assert W.STAGE_TTL_SECONDS == boqimport.STAGE_TTL_SECONDS == IS.STAGE_TTL_SECONDS == 24 * 3600
    assert W.MAX_STAGED_PER_USER == boqimport.MAX_STAGED_PER_USER == IS.MAX_STAGED_PER_USER
    from conftest import ensure_test_user
    tok = W.stage(_sheet(ONE_RATE), "x.xlsx", ensure_test_user()["id"])
    row = STORE["wo_imports"][tok]
    assert row["id"] == row["token"] == tok
    assert {"user_id", "created_at", "created_ts", "filename", "format", "sheets",
            "grid", "sheet_index", "mapping"} <= set(row)
    assert "wb" not in row                               # the grid, never the workbook


def test_a_staged_import_survives_a_new_process(client, fake_db):
    """
    Stage in one request; persist through `db.sync()` exactly as a teardown
    does; empty the store as a restarted process's RAM is; load it back as
    `db.load_into()` does at boot; and complete the mapping from a FRESH test
    client. The staged row is the only thing that crossed.
    """
    import app as app_module
    from conftest import ensure_test_user
    data = _xlsx([["S.No", "Description of Work", "Unit", "Qty", "Material Rate",
                   "Labour Rate"], [1, "Core cutting", "nos", 12, 0, 350],
                  [2, "Hanger supports", "nos", 40, 85, 30]])
    r = client.post("/wo/import", data={"workbook": (io.BytesIO(data), "wo.xlsx")},
                    content_type="multipart/form-data")
    tok = r.headers["Location"].rsplit("/", 1)[-1]
    assert tok in STORE["wo_imports"]

    db.sync({c: dict(STORE.get(c) or {}) for c in db.COLLECTIONS})
    assert tok in fake_db.rows["wo_imports"]             # it reached the database
    STORE["wo_imports"].clear()                          # a new process: RAM empty
    fresh = {c: {} for c in db.COLLECTIONS}
    db.load_into(fresh)                                  # ...and the boot load
    STORE["wo_imports"].update(fresh["wo_imports"])

    with app_module.app.test_client() as c2:
        with c2.session_transaction() as sess:
            sess[auth.SESSION_KEY] = ensure_test_user()["id"]
        sel = STORE["wo_imports"][tok]["sheet_index"]
        grid = W._grid(STORE["wo_imports"][tok])
        form = {f"map_{sel}_{k}": v for k, v in W.guess_mapping(grid).items()}
        form.update(tab=[str(sel)], act="confirm")
        html = c2.post(f"/wo/import/{tok}", data=form).get_data(as_text=True)
    assert "Core cutting" in _body(html) and "Hanger supports" in _body(html)
    assert _priced(html, "ln_mrate") == ["0", "85"]
    assert _priced(html, "ln_lrate") == ["350", "30"]
    assert tok not in STORE["wo_imports"]                # consumed


def test_without_the_persisted_row_the_token_is_gone(client):
    """The control for the test above: it is the stored row that carries it."""
    from conftest import ensure_test_user
    tok = W.stage(_sheet(ONE_RATE), "x.xlsx", ensure_test_user()["id"])
    STORE["wo_imports"].clear()
    r = client.get(f"/wo/import/{tok}")
    assert r.status_code == 302 and "expired+or+is+not+yours" in r.headers["Location"]


def test_a_staged_row_expires_after_the_boq_ttl_and_the_cap_is_per_collection(client):
    from conftest import ensure_test_user
    import boqimport
    uid = ensure_test_user()["id"]
    old = W.stage(_sheet(ONE_RATE), "old.xlsx", uid)
    STORE["wo_imports"][old]["created_ts"] -= W.STAGE_TTL_SECONDS + 1
    client.get("/wo/import")                              # every request purges
    assert old not in STORE["wo_imports"]
    boq_toks = [boqimport.stage(_sheet(ONE_RATE), f"b{i}.xlsx", uid)[0] for i in range(3)]
    wo_toks = [W.stage(_sheet(ONE_RATE), f"w{i}.xlsx", uid) for i in range(4)]
    assert len(STORE["wo_imports"]) == W.MAX_STAGED_PER_USER   # its own cap...
    assert wo_toks[0] not in STORE["wo_imports"]
    assert all(t in STORE["boq_imports"] for t in boq_toks)    # ...never the BOQ's
    STORE["boq_imports"].clear()
    STORE["import_layouts"].clear()


# ══ FIX 2 (5 Oct 2026) — heading rows are HEADER lines ════════════════════════

TWO_SECTIONS = [
    ["Sr. No.", "Description", "Unit", "Qty", "Material Rate", "Labour Rate"],
    ["A", "CIVIL WORKS", None, None, None, None],
    ["1", "Excavation", "cum", 10, 100, 50],
    ["2", "Pipe work", None, None, None, None],
    ["2.1", "50 NB pipe", "m", 5, 400, 90],
    ["B", "ELECTRICAL WORKS", None, None, None, None],
    ["1", "Cabling", "m", 20, 30, 10],
]


def _form_back(html, **header):
    """Post the prefilled form back exactly as rendered — no edit at all."""
    body = _body(html)
    data = {"date": "2026-10-05", "contractor_name": "Ravi", **header}
    for name in ("ln_id", "ln_note", "ln_hdr", "ln_sec", "ln_item", "ln_unit",
                 "ln_qty", "ln_mrate", "ln_lrate"):
        data[name] = re.findall(rf'name="{name}" value="([^"]*)"', body)
    data["ln_desc"] = [__import__("html").unescape(t) for t in
                       re.findall(r'<textarea name="ln_desc"[^>]*>(.*?)</textarea>', body, re.S)]
    return data


def test_a_sheet_with_two_section_headings_saves_without_any_edit(client):
    _tok, r = _confirm(client, _sheet(TWO_SECTIONS))
    html = r.get_data(as_text=True)
    assert _values(html, "ln_hdr") == ["1", "0", "1", "0", "1", "0"]
    assert _values(html, "ln_item") == ["A", "1", "2", "2.1", "B", "1"]
    assert 'class="wo-need"' not in _body(html)          # nothing to answer
    assert "3 lines and 3 headings" in html
    r = client.post("/wo/create", data=_form_back(html))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    (wo,) = STORE["work_orders"].values()
    heads = [(l["item_no"], l["description"]) for l in wo["lines"] if l["is_header"]]
    assert heads == [("A", "CIVIL WORKS"), ("2", "Pipe work"), ("B", "ELECTRICAL WORKS")]
    for l in wo["lines"]:
        if l["is_header"]:
            assert (l["unit"], l["qty"], l["material_rate"], l["labour_rate"]) == ("", None, None, None)
    # R4 (5 Oct 2026): the sheet's two section titles are SECTION headings.
    assert [l["description"] for l in wo["lines"] if W.is_section(l)] == [
        "CIVIL WORKS", "ELECTRICAL WORKS"]
    # 10x100 + 5x400 + 20x30 material; 10x50 + 5x90 + 20x10 labour.
    t = W.totals_of(wo)
    assert (t["material"], t["labour"], t["grand"]) == (3600.0, 1150.0, 4750.0)


def test_a_section_code_the_sheet_never_wrote_is_not_printed():
    rows = [["Sr. No.", "Description", "Unit", "Qty", "Material Rate", "Labour Rate"],
            [None, "CIVIL WORKS", None, None, None, None],
            ["1", "Excavation", "cum", 10, 100, 50]]
    wb = _sheet(rows)
    grid = wb["grid"][0]
    m = W.guess_mapping(grid)
    result = SI.build(grid, {c: W._TO_SI.get(t, "") for c, t in m.items()})
    out = W.rows_from_build(result, m, W.item_column_values(grid, m))
    heads = [(r["item_no"], r["description"]) for r in out if r["is_header"]]
    assert all(item == "" for item, _d in heads)


def test_headers_are_excluded_from_every_total_even_carrying_stray_figures(client):
    data = {"date": "2026-10-05", "contractor_name": "Ravi",
            "ln_id": ["", ""], "ln_note": ["", ""], "ln_hdr": ["1", "0"],
            "ln_item": ["A", "1"], "ln_desc": ["CIVIL WORKS", "Excavation"],
            "ln_unit": ["m", "cum"], "ln_qty": ["99", "10"],
            "ln_mrate": ["99", "100"], "ln_lrate": ["99", "50"]}
    assert client.post("/wo/create", data=data).status_code == 302
    (wo,) = STORE["work_orders"].values()
    head = wo["lines"][0]
    assert head["is_header"] and (head["unit"], head["qty"], head["material_rate"],
                                  head["labour_rate"]) == ("", None, None, None)
    t = W.totals_of(wo)
    assert (t["material"], t["labour"], t["grand"]) == (1000.0, 500.0, 1500.0)
    # A stray figure written onto a heading by hand is still never summed.
    head.update(qty=5, material_rate=7, labour_rate=7)
    assert W.totals_of(wo)["grand"] == 1500.0
    html = client.get("/wo/").get_data(as_text=True)
    assert ">1,500.00<" in html


def test_the_print_and_the_view_show_a_heading_the_way_the_boq_print_does(client):
    data = {"date": "2026-10-05", "contractor_name": "Ravi",
            "ln_id": ["", "", ""], "ln_note": ["", "", ""], "ln_hdr": ["1", "0", "0"],
            "ln_item": ["A", "", ""], "ln_desc": ["CIVIL WORKS", "Excavation", "Backfill"],
            "ln_unit": ["", "cum", "cum"], "ln_qty": ["", "10", "2"],
            "ln_mrate": ["", "100", "5"], "ln_lrate": ["", "50", "5"]}
    client.post("/wo/create", data=data)
    (wid,) = STORE["work_orders"]
    for url in (f"/wo/print/{wid}", f"/wo/view/{wid}"):
        html = client.get(url).get_data(as_text=True)
        assert ('<tr class="row-assembly">\n          <td class="c-sno">A</td>\n'
                '          <td colspan="7" class="c-desc">CIVIL WORKS</td>') in html.replace("\r\n", "\n"), url
        # The priced lines are numbered 1 and 2: a heading takes no position.
        assert re.findall(r'<td class="c-sno">([^<]*)</td>', html) == ["A", "1", "2"]
    # 10x100 + 2x5 material, 10x50 + 2x5 labour — the heading adds nothing.
    assert ">1,010.00<" in html and ">510.00<" in html and ">1,520.00<" in html
    assert "Grand Total (Material + Labour)" in html


def test_a_real_line_with_a_blank_rate_is_still_refused_beside_a_heading(client):
    data = {"date": "2026-10-05", "contractor_name": "Ravi",
            "ln_id": ["", ""], "ln_note": ["", ""], "ln_hdr": ["1", "0"],
            "ln_item": ["A", "1"], "ln_desc": ["CIVIL WORKS", "Excavation"],
            "ln_unit": ["", "cum"], "ln_qty": ["", "10"],
            "ln_mrate": ["", "100"], "ln_lrate": ["", ""]}
    html = client.post("/wo/create", data=data).get_data(as_text=True)
    assert not STORE["work_orders"]
    assert "Line 2: needs a labour rate" in html and "Line 1:" not in html


def test_a_heading_alone_is_not_a_work_order_and_a_heading_needs_words(client):
    base = {"date": "2026-10-05", "contractor_name": "Ravi", "ln_id": [""],
            "ln_note": [""], "ln_hdr": ["1"], "ln_unit": [""], "ln_qty": [""],
            "ln_mrate": [""], "ln_lrate": [""]}
    html = client.post("/wo/create", data={**base, "ln_item": ["A"],
                                            "ln_desc": ["CIVIL"]}).get_data(as_text=True)
    assert "a heading alone orders nothing" in html and not STORE["work_orders"]
    html = client.post("/wo/create", data={**base, "ln_hdr": ["1", "0"], "ln_id": ["", ""],
                                            "ln_note": ["", ""], "ln_item": ["A", "1"],
                                            "ln_desc": ["", "Dig"], "ln_unit": ["", "m"],
                                            "ln_qty": ["", "1"], "ln_mrate": ["", "1"],
                                            "ln_lrate": ["", "1"]}).get_data(as_text=True)
    assert "Line 1: needs a description" in html and not STORE["work_orders"]


def test_headings_are_added_and_deleted_by_hand_on_the_form(client):
    html = client.get("/wo/create").get_data(as_text=True)
    assert '<template id="wo-hd-tpl">' in html and "woAddHeading()" in html
    tpl = html[html.index('<template id="wo-hd-tpl">'):]
    assert 'name="ln_hdr" value="1"' in tpl[:tpl.index("</template>")]
    data = {"date": "2026-10-05", "contractor_name": "Ravi",
            "ln_id": ["", ""], "ln_note": ["", ""], "ln_hdr": ["1", "0"],
            "ln_item": ["A", "1"], "ln_desc": ["CIVIL WORKS", "Excavation"],
            "ln_unit": ["", "cum"], "ln_qty": ["", "10"],
            "ln_mrate": ["", "100"], "ln_lrate": ["", "50"]}
    client.post("/wo/create", data=data)
    (wid,) = STORE["work_orders"]
    keep = STORE["work_orders"][wid]["lines"][1]["line_id"]
    edit = client.get(f"/wo/edit/{wid}").get_data(as_text=True)
    assert _values(edit, "ln_hdr") == ["1", "0"]               # it comes back a heading
    # Delete the heading on the form: post only the priced row.
    r = client.post(f"/wo/edit/{wid}", data={
        "date": "2026-10-05", "contractor_name": "Ravi", "ln_id": [keep],
        "ln_note": [""], "ln_hdr": ["0"], "ln_item": ["1"], "ln_desc": ["Excavation"],
        "ln_unit": ["cum"], "ln_qty": ["10"], "ln_mrate": ["100"], "ln_lrate": ["50"]})
    assert r.status_code == 302
    lines = STORE["work_orders"][wid]["lines"]
    assert [l["is_header"] for l in lines] == [False] and lines[0]["line_id"] == keep


# ══ FIX 3 (5 Oct 2026) — ruling G, verified ═══════════════════════════════════

def test_a_contractor_can_be_typed_with_no_address_book_entry_at_all(client):
    """(a) Name, address, GSTIN and phone — the book emptied first."""
    saved = dict(STORE["addresses"])
    STORE["addresses"].clear()
    try:
        assert "No contractor is filed" in client.get("/wo/create").get_data(as_text=True)
        wid = _create(client, contractor_id="", contractor_name="Sai Painters",
                      contractor_addr="Shop 3, Wakad\nPune 411057",
                      contractor_gstin="27aaapz1234c1zv", contractor_phone="+91 98200 11111")
        assert not STORE["addresses"]                    # nothing was filed
        wo = STORE["work_orders"][wid]
        assert (wo["contractor_id"], wo["contractor_source"], wo["contractor_name"]) == (
            "", "typed", "Sai Painters")
        assert wo["to"] == "Sai Painters\nShop 3, Wakad\nPune 411057"
        assert wo["contractor_gstin"] == "27AAAPZ1234C1ZV"
        assert wo["contractor_phone"] == "+91 98200 11111"
        html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
        for text in ("Sai Painters", "Shop 3, Wakad", "27AAAPZ1234C1ZV", "+91 98200 11111"):
            assert text in html, text
        edit = client.get(f"/wo/edit/{wid}").get_data(as_text=True)
        assert 'value="+91 98200 11111"' in edit           # handed back on edit
    finally:
        STORE["addresses"].clear()
        STORE["addresses"].update(saved)


def test_a_picked_contractor_snapshots_the_same_fields_phone_included(client):
    con = _contractor()
    STORE["addresses"][con]["phone"] = "020 2712 0000"
    wid = _create(client, contractor_id=con, contractor_name="")
    wo = STORE["work_orders"][wid]
    assert wo["contractor_phone"] == "020 2712 0000"
    typed = STORE["work_orders"][_create(client)]
    assert set(wo) == set(typed)                         # the same snapshot shape
    STORE["addresses"][con]["phone"] = "changed"
    assert "020 2712 0000" in client.get(f"/wo/print/{wid}").get_data(as_text=True)


def test_a_work_order_with_no_phone_prints_no_phone_row(client):
    wid = _create(client)
    assert "Your Phone" not in client.get(f"/wo/print/{wid}").get_data(as_text=True)


def test_gstin_auto_fill_is_not_gated_by_type_anywhere(client):
    """(b) The lookup route takes no type; the form's script special-cases only
    `site`; a contractor's form carries the same GST widget a vendor's does."""
    import address
    import test_gst_lookup as TG
    address.ensure_demo_addresses()
    TG.plant()
    res = client.post("/address/gst/lookup", data={"gstin": TG.GOOD}).get_json()
    assert res["ok"] and res["result"]["gstin"] == TG.GOOD
    add = client.get("/address/add").get_data(as_text=True)
    assert "var NO_ADDRESS_FILL = 'site';" in add
    assert add.count("NO_ADDRESS_FILL") >= 1 and "'contractor'" not in add
    vendor = next(a for a, r in STORE["addresses"].items() if r.get("type") == "vendor")
    con = _contractor()
    v_html = client.get(f"/address/edit/{vendor}").get_data(as_text=True)
    c_html = client.get(f"/address/edit/{con}").get_data(as_text=True)
    for marker in ('id="gst-captcha"', '"lookup": ', "NO_ADDRESS_FILL"):
        assert (marker in v_html) == (marker in c_html), marker


# ══ PASS 3 (5 Oct 2026) — the client's real sheet: R1, R4, R5, R6, R7 ═════════
#
# CLIENT_CHANGES.md §0, forty-third block. The import half — the header band
# (R2), quantity-0 rows (R3), several tabs (R4) — and the acceptance on the
# client's own file are tests/test_wo_nxtra.py. These are the form, the record
# and the print.

def _rows3(*rows):
    """Form fields for (kind, item, desc, unit, qty, mrate, lrate) — kind ""
    a priced line, "h" a heading, "s" a SECTION heading — posted the way the
    form posts them, every list aligned row for row."""
    out = {k: [] for k in ("ln_id", "ln_hdr", "ln_sec", "ln_item", "ln_desc",
                           "ln_unit", "ln_qty", "ln_mrate", "ln_lrate", "ln_note")}
    for kind, item, desc, unit, qty, m, l in rows:
        out["ln_id"].append("")
        out["ln_hdr"].append("1" if kind else "0")
        out["ln_sec"].append("1" if kind == "s" else "0")
        out["ln_item"].append(item)
        out["ln_desc"].append(desc)
        out["ln_unit"].append(unit)
        out["ln_qty"].append(qty)
        out["ln_mrate"].append(m)
        out["ln_lrate"].append(l)
        out["ln_note"].append("")
    return out


def _post(client, rows, url="/wo/create", **over):
    data = {"date": "2026-10-05", "contractor_id": "", "contractor_name": "Ravi",
            "contractor_gstin": "", "contractor_addr": "Pune", "project_id": "",
            "notes": "", "tracks": "both", "gst_rate": "18", "site": "", "terms": ""}
    data.update(_rows3(*rows))
    data.update(over)
    return client.post(url, data=data)


def _raised(client, rows, **over):
    r = _post(client, rows, **over)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    (wid,) = [k for k in STORE["work_orders"] if k != GOLD_WO][-1:]
    return wid, STORE["work_orders"][wid]


def _gst_box(html):
    return re.search(r'id="gst_rate" name="gst_rate"[^>]*value="([^"]*)"', html, re.S).group(1)


def _sums(html):
    """Every summing row of a print — (label, the amount in its last cell)."""
    flat = re.sub(r"\s+", " ", html)
    return re.findall(r'<td colspan="4" class="sum-lbl">([^<]*)</td>'
                      r'(?: <td class="c-(?:price|total)">[^<]*</td>)*?'
                      r' <td class="c-total">([^<]+)</td> </tr>', flat)


SECTIONED = (
    ("s", "A", "CIVIL WORKS", "", "", "", ""),
    ("",  "1", "Excavation", "cum", "10", "", "50"),
    ("h", "2", "Pipe work", "", "", "", ""),
    ("",  "2.1", "50 NB pipe", "m", "5", "", "90"),
    ("s", "B", "ELECTRICAL WORKS", "", "", "", ""),
    ("",  "1", "Cabling", "m", "20", "", "10"),
)


# ── R1 — the tracks are declared per work order ──────────────────────────────

def test_r1_a_rate_typed_in_a_track_the_work_order_does_not_carry_is_refused_naming_the_lines(client):
    rows = (("", "1", "Pipe laying", "m", "10", "100", "50"),
            ("", "2", "Painting", "sqm", "2", "", "40"),
            ("", "3", "Hangers", "Nos", "4", "0", "15"))
    r = _post(client, rows, tracks="labour")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and not STORE["work_orders"]       # nothing saved
    assert ("Material rates are typed on 2 lines (lines 1, 3) but this work "
            "order is Labour only: clear them, or choose Material + Labour.") in html
    # Never silently dropped: the refused figures are still on the page.
    assert _values(html, "ln_mrate") == ["100", "", "0"]
    # Cleared, it saves — and the other track is stored ABSENT, never 0.
    wid, wo = _raised(client, tuple(r_[:5] + ("",) + r_[6:] for r_ in rows),
                      tracks="labour")
    assert wo["tracks"] == "labour"
    assert [l["labour_rate"] for l in wo["lines"]] == [50.0, 40.0, 15.0]
    assert not any("material_rate" in l for l in wo["lines"])


def test_r1_the_mirror_a_material_only_work_order_refuses_a_labour_figure():
    rows = [{"item_no": "1", "description": "Pipe", "unit": "m", "qty": "1",
             "material_rate": "5", "labour_rate": "2"},
            # A heading's figures are dropped, never a stray: not named.
            {"item_no": "A", "description": "Civil", "is_header": True,
             "labour_rate": "9"}]
    _lines_, problems = W.lines_from_rows(rows, tracks="material")
    assert [p["message"] for p in problems if p["row"] is None] == [
        "Labour rates are typed on 1 line (line 1) but this work order is "
        "Material only: clear them, or choose Material + Labour."]
    assert [(p["row"], p["field"]) for p in problems if p["row"] is not None] == [
        (0, "labour_rate")]


def test_r1_a_one_track_work_order_still_refuses_a_blank_rate_on_its_own_track(client):
    r = _post(client, (("", "1", "Pipe laying", "m", "10", "", ""),), tracks="labour")
    assert r.status_code == 200 and not STORE["work_orders"]
    assert "needs a labour rate — type 0 if there is none" in r.get_data(as_text=True)
    assert "needs a material rate" not in r.get_data(as_text=True)


def test_r1_update_the_rate_columns_redraws_the_form_and_saves_nothing(client):
    rows = (("", "1", "Pipe laying", "m", "10", "", "50"),)
    html = _post(client, rows, tracks="labour", act="retrack").get_data(as_text=True)
    assert not STORE["work_orders"]
    assert 'name="ln_mrate"' not in html and 'name="ln_lrate"' in html
    assert "The lines now carry Labour only." in html
    assert '<option value="labour" selected>' in html
    # A material figure already typed stays ON THE PAGE, named — never dropped.
    rows = (("", "1", "Pipe laying", "m", "10", "100", "50"),)
    html = _post(client, rows, tracks="labour", act="retrack").get_data(as_text=True)
    assert _values(html, "ln_mrate") == ["100"]
    assert "Material rates are typed on 1 line (line 1)" in html
    assert not STORE["work_orders"]


def test_r1_r5_a_work_order_stored_before_pass_3_reads_as_both_tracks_and_no_gst(client, golden_wo):
    wo = STORE["work_orders"][GOLD_WO]
    assert not {"tracks", "gst_rate", "site", "terms"} & set(wo)
    assert W.tracks_of(wo) == "both" and W.gst_rate_of(wo) == 0.0
    t = W.totals_of(wo)
    assert (t["gst_rate"], t["gst"], t["total"]) == (0.0, 0.0, t["grand"])
    html = client.get(f"/wo/print/{GOLD_WO}").get_data(as_text=True)
    for word in ("GST @", "Total (incl. GST)", "Subtotal - ", ">Summary<",
                 '<span class="m-lbl">Site</span>', "Terms &amp; Conditions",
                 "Labour only", "Material only"):
        assert word not in html, word
    # An unrecognised value hides nothing: it reads as both.
    assert W.tracks_of({"tracks": " LABOUR "}) == "labour"
    assert W.tracks_of({"tracks": "half"}) == "both"


def test_r5_a_legacy_draft_opens_its_gst_box_at_0_and_a_resave_keeps_no_gst(client):
    wid = _create(client)
    wo = STORE["work_orders"][wid]
    for k in ("tracks", "gst_rate", "site", "terms"):
        wo.pop(k, None)
    html = client.get(f"/wo/edit/{wid}").get_data(as_text=True)
    assert _gst_box(html) == "0" and '<option value="both" selected>' in html
    r = client.post(f"/wo/edit/{wid}", data={**_form_back(html), "tracks": "both",
                                              "gst_rate": _gst_box(html)})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert wo["gst_rate"] == 0.0 and wo["tracks"] == "both"
    assert "GST @" not in client.get(f"/wo/print/{wid}").get_data(as_text=True)


# ── R5 — GST, derived ────────────────────────────────────────────────────────

def test_r5_a_new_work_order_opens_with_both_tracks_and_gst_at_18(client):
    html = client.get("/wo/create").get_data(as_text=True)
    assert _gst_box(html) == "18"
    assert '<option value="both" selected>' in html
    assert '<textarea id="terms" name="terms" rows="4"></textarea>' in html


@pytest.mark.parametrize("lines,rate,want", [
    # 3 x 333.33 = 999.99; x 18% = 179.9982 -> 180.00.
    ([{"qty": 3.0, "labour_rate": 333.33}], 18, (999.99, 180.0, 1179.99)),
    # Both tracks: the tax is on the PRE-TAX grand total, not per track.
    ([{"qty": 1.0, "material_rate": 1000.0, "labour_rate": 234.57}], 12.5,
     (1234.57, 154.32, 1388.89)),
    # ⚠ 12.5 x 1% is EXACTLY 0.125 and rounds to 0.12 — `round(x, 2)`, the
    #   purchase order's house rule, half-to-even on an exact binary half.
    #   Pinned, not chosen.
    ([{"qty": 1.0, "labour_rate": 12.5}], 1, (12.5, 0.12, 12.62)),
    ([{"qty": 2.0, "labour_rate": 50.0}], 0, (100.0, 0.0, 100.0)),
    # Stored out of range, it is clamped to 0..100 — never a negative tax,
    # never more than the work itself.
    ([{"qty": 2.0, "labour_rate": 50.0}], -5, (100.0, 0.0, 100.0)),
    ([{"qty": 2.0, "labour_rate": 50.0}], 150, (100.0, 100.0, 200.0)),
])
def test_r5_gst_is_derived_from_the_pre_tax_total_and_rounded_once(lines, rate, want):
    t = W.totals_of({"gst_rate": rate, "lines": lines})
    assert (t["grand"], t["gst"], t["total"]) == want
    assert t["gst_rate"] == max(0, min(100, rate))


@pytest.mark.parametrize("raw,fragment", [
    ("", "GST rate: type a figure from 0 to 100 — 0 when this work order carries no GST."),
    ("101", "GST rate: a figure from 0 to 100, please."),
    ("-1", "GST rate: a figure from 0 to 100, please."),
    ("abc", "GST rate: a figure from 0 to 100, please."),
    ("nan", "GST rate: a figure from 0 to 100, please."),
])
def test_r5_the_gst_rate_is_a_typed_figure_from_0_to_100_and_blank_is_refused(client, raw, fragment):
    r = _post(client, (("", "1", "Pipe", "m", "1", "1", "1"),), gst_rate=raw)
    assert r.status_code == 200 and not STORE["work_orders"]
    assert fragment in r.get_data(as_text=True)


def test_r5_the_rate_is_stored_the_tax_never_is_and_a_changed_rate_changes_the_print(client):
    wid, wo = _raised(client, (("", "1", "Pipe", "m", "10", "100", "50"),), gst_rate="18%")
    assert wo["gst_rate"] == 18.0
    assert not {"gst", "gst_amount", "tax", "total", "grand_total"} & set(wo)
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert _sums(html) == [("Total", "500.00"), ("Grand Total (Material + Labour)", "1,500.00"),
                           ("GST @ 18%", "270.00"), ("Total (incl. GST)", "1,770.00")]
    # The amount in words is the figure the contractor is owed: incl. GST.
    assert "One Thousand Seven Hundred Seventy" in html
    wo["gst_rate"] = 12
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert ("GST @ 12%", "180.00") in _sums(html)
    # The register and the project panel show the value incl. GST.
    assert "1,680.00" in client.get("/wo/").get_data(as_text=True)


# ── R4 — sections, subtotals and the summary ─────────────────────────────────

def test_r4_sections_close_with_a_subtotal_and_a_summary_sits_above_the_totals(client):
    wid, wo = _raised(client, SECTIONED, tracks="labour")
    assert [l["description"] for l in wo["lines"] if W.is_section(l)] == [
        "CIVIL WORKS", "ELECTRICAL WORKS"]
    assert not W.is_section(wo["lines"][2])                  # a plain heading
    assert [(g["title"], g["grand"]) for g in W.section_groups(wo)] == [
        ("CIVIL WORKS", 950.0), ("ELECTRICAL WORKS", 200.0)]
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert _sums(html) == [
        ("Subtotal - CIVIL WORKS", "950.00"), ("Subtotal - ELECTRICAL WORKS", "200.00"),
        ("CIVIL WORKS", "950.00"), ("ELECTRICAL WORKS", "200.00"),
        ("Total", "1,150.00"), ("GST @ 18%", "207.00"), ("Total (incl. GST)", "1,357.00")]
    flat = re.sub(r"\s+", " ", html)
    # Each subtotal closes its own group: after its last line, before the next.
    assert flat.index("50 NB pipe") < flat.index("Subtotal - CIVIL WORKS") \
        < flat.index('class="c-desc">ELECTRICAL WORKS<') < flat.index("Subtotal - ELECTRICAL")
    assert flat.index("Subtotal - ELECTRICAL") < flat.index('class="c-desc">Summary<') \
        < flat.index('class="sum-lbl">Total<')
    assert '<tr class="row-total row-sum"> <td colspan="4" class="sum-lbl">Total (incl. GST)' in flat
    assert '<tr class="row-sum"> <td colspan="4" class="sum-lbl">Total</td>' in flat
    assert re.findall(r'<th class="c-[a-z]+">([^<]*)</th>', html) == [
        "Sr", "Description", "Unit", "Qty", "Rate", "Amount"]
    assert "Work assigned to contractor &mdash; Labour only" in html
    assert "One Thousand Three Hundred Fifty Seven" in html


def test_r4_a_both_track_work_order_subtotals_each_track_under_its_own_column(client):
    rows = tuple(r_[:5] + ((str(int(r_[4]) * 10) if r_[4] else ""),) + r_[6:]
                 for r_ in SECTIONED)
    wid, _wo = _raised(client, rows, tracks="both", gst_rate="0")
    flat = re.sub(r"\s+", " ", client.get(f"/wo/print/{wid}").get_data(as_text=True))
    # Material: 10x100 + 5x50 = 1,250 | 20x200 = 4,000. Labour as above.
    assert ('Subtotal - CIVIL WORKS</td> <td class="c-price"></td> <td class="c-total">'
            '1,250.00</td> <td class="c-price"></td> <td class="c-total">950.00</td>') in flat
    assert ('Subtotal - ELECTRICAL WORKS</td> <td class="c-price"></td> <td class="c-total">'
            '4,000.00</td> <td class="c-price"></td> <td class="c-total">200.00</td>') in flat
    assert ("CIVIL WORKS", "2,200.00") in _sums(flat) and ("ELECTRICAL WORKS", "4,200.00") in _sums(flat)
    assert _sums(flat)[-1] == ("Grand Total (Material + Labour)", "6,400.00")
    assert "GST @" not in flat                                     # typed 0: no GST


def test_r4_lines_above_the_first_section_are_a_group_of_their_own(client):
    rows = (("", "0", "Mobilisation", "LS", "1", "", "500"),) + SECTIONED
    wid, _wo = _raised(client, rows, tracks="labour")
    sums = _sums(client.get(f"/wo/print/{wid}").get_data(as_text=True))
    assert sums[0] == ("Subtotal - Lines before the first section", "500.00")
    assert ("Lines before the first section", "500.00") in sums
    assert ("Total", "1,650.00") in sums


def test_r4_a_work_order_with_no_section_prints_no_subtotal_and_no_summary(client):
    # The tick posted on every PRICED line and on no heading: a tick means
    # something on a heading only, so nothing is a section.
    data = _rows3(*SECTIONED)
    data["ln_sec"] = ["1" if h == "0" else "0" for h in data["ln_hdr"]]
    r = _post(client, (), tracks="labour", **data)
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    (wid, wo), = STORE["work_orders"].items()
    assert not any(W.is_section(l) for l in wo["lines"]) and W.section_groups(wo) == []
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert "Subtotal - " not in html and ">Summary<" not in html
    assert [s[0] for s in _sums(html)] == ["Total", "GST @ 18%", "Total (incl. GST)"]


def test_r4_the_form_carries_the_section_tick_on_headings_only(client):
    wid, _wo = _raised(client, SECTIONED, tracks="labour")
    html = client.get(f"/wo/edit/{wid}").get_data(as_text=True)
    body = _body(html)
    assert body.count('class="wo-sec-box" checked') == 2
    assert body.count('class="wo-sec-box"') == 3                  # three headings
    assert _values(html, "ln_sec") == ["1", "0", "0", "0", "1", "0"]
    assert "Section (subtotal)" in body


# ── R6 — site; R7 — terms ────────────────────────────────────────────────────

def test_r6_the_site_prints_in_the_header_block_only_when_there_is_one(client):
    wid, wo = _raised(client, (("", "1", "Pipe", "m", "1", "1", "1"),),
                      site="  Nxtra Data Centre, Lucknow  ")
    assert wo["site"] == "Nxtra Data Centre, Lucknow"
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    cell = ('<div class="mrow"><span class="m-lbl">Site</span>'
            '<span class="m-val">Nxtra Data Centre, Lucknow</span></div>')
    assert cell in html
    assert html.index('<span class="m-lbl">Date</span>') < html.index(cell) \
        < html.index('<span class="m-lbl">Our GSTIN</span>')
    wid, wo = _raised(client, (("", "1", "Pipe", "m", "1", "1", "1"),), site="x" * 300)
    assert wo["site"] == "x" * W.MAX_SITE_CHARS
    wo["site"] = "   "
    assert '<span class="m-lbl">Site</span>' not in client.get(f"/wo/print/{wid}").get_data(as_text=True)


def test_r7_terms_are_one_per_line_and_print_numbered_after_the_totals(client):
    terms = ("Payment 30 days after measurement\r\n\r\n   Debris cleared daily "
             "by the contractor  \nTools and tackles by the contractor\n")
    wid, wo = _raised(client, (("", "1", "Pipe", "m", "1", "1", "1"),), terms=terms)
    assert wo["terms"] == ("Payment 30 days after measurement\nDebris cleared daily "
                           "by the contractor\nTools and tackles by the contractor")
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    assert re.findall(r'<span class="tnc-num">(\d+)\.</span><span>([^<]*)</span>', html) == [
        ("1", "Payment 30 days after measurement"),
        ("2", "Debris cleared daily by the contractor"),
        ("3", "Tools and tackles by the contractor")]
    assert html.index("Work Order Value (in words)") < html.index("Terms &amp; Conditions")
    wid, _wo = _raised(client, (("", "1", "Pipe", "m", "1", "1", "1"),))
    assert "Terms &amp; Conditions" not in client.get(f"/wo/print/{wid}").get_data(as_text=True)


def test_r7_new_work_orders_prefill_the_default_terms_from_their_own_settings_record(client):
    assert SET.wo_default_terms() == ""                         # empty by default
    r = client.post("/settings/", data={"wo_prefix": "", "wo_next_no": "",
                                        "wo_default_terms": "Payment in 30 days\r\n\r\n"
                                                            "  Tools by the contractor "})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    want = "Payment in 30 days\nTools by the contractor"
    assert SET.wo_default_terms() == want
    assert f'name="wo_default_terms" rows="4">{want}</textarea>' in \
        client.get("/settings/").get_data(as_text=True)
    assert f'<textarea id="terms" name="terms" rows="4">{want}</textarea>' in \
        client.get("/wo/create").get_data(as_text=True)
    # The import's form opens with them too.
    _tok, r = _confirm(client, _sheet(ONE_RATE))
    assert f'<textarea id="terms" name="terms" rows="4">{want}</textarea>' in r.get_data(as_text=True)

    wid, wo = _raised(client, (("", "1", "Pipe", "m", "1", "1", "1"),), terms=want)
    # Spending the number writes the series back; the terms stay.
    assert SET.wo_series()["next_no"] == "2" and SET.wo_default_terms() == want
    # A work order's terms are its OWN: a later default does not reach it.
    SET.save_wo_series("", "2", default_terms="Something else")
    assert wo["terms"] == want
    assert want in client.get(f"/wo/edit/{wid}").get_data(as_text=True)
    SET.save_wo_series("", "2", default_terms="")
    assert SET.wo_default_terms() == ""


# ── Escaping — the section title, the site and the terms ─────────────────────

def test_r4_r6_r7_a_section_title_the_site_and_the_terms_reach_every_page_escaped(client):
    rows = (("s", "A", "Sec " + PAYLOAD, "", "", "", ""),
            ("", "1", "Pipe", "m", "1", "", "5"))
    wid, _wo = _raised(client, rows, tracks="labour", site="Site " + PAYLOAD,
                       terms="Term " + PAYLOAD + "\nSecond " + PAYLOAD)
    for url in (f"/wo/view/{wid}", f"/wo/print/{wid}", f"/wo/edit/{wid}", "/wo/"):
        html = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html, url
        assert "<img src=x onerror=alert(2)>" not in html, url
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    for text in ("Subtotal - Sec &lt;script&gt;", "Site &lt;script&gt;",
                 "Term &lt;script&gt;", "Second &lt;script&gt;"):
        assert text in html, text
    # …and on a refused form, which hands back what was typed.
    r = _post(client, rows, tracks="labour", gst_rate="", site="Site " + PAYLOAD,
              terms="Term " + PAYLOAD)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "<script>alert(1)</script>" not in html
    assert "Site &lt;script&gt;" in html and "Term &lt;script&gt;" in html


# ── The two new print goldens ────────────────────────────────────────────────

GOLD_WO_LABOUR = "gold-wo-labour"
GOLD_WO_BOTH = "gold-wo-both-gst"


@pytest.fixture()
def golden_wo_pass3(client, pinned_identity):
    """
    (a) labour only, with sections, GST, a site and terms; (b) both tracks
    with GST. Every value written here — nothing derived from today.
    """
    head = {
        "date": "2026-10-05", "status": "issued", "issued_on": "2026-10-06",
        "contractor_id": "", "contractor_name": "Ravi Fabricators Pvt Ltd",
        "contractor_source": "typed",
        "to": "Ravi Fabricators Pvt Ltd\nShed 4, MIDC Bhosari\nPune 411026",
        "contractor_gstin": "27AAAPZ1234C1ZV",
        "project_id": "proj-gold", "project_name": "Kohinoor Techpark",
        "notes": "Work to be completed within 30 days of issue.",
        "created_at": "2026-10-05 10:00", "created_by": "",
        "updated_at": "2026-10-05 10:00",
    }
    STORE["work_orders"][GOLD_WO_LABOUR] = {
        **head, "id": GOLD_WO_LABOUR, "ref": "SF/WO/0002",
        "tracks": "labour", "gst_rate": 18.0, "site": "Nxtra Data Centre, Lucknow",
        "terms": "Payment 30 days after measurement\nTools and tackles by the contractor",
        "lines": [
            {"line_id": "bbbbbbbbbbb1", "is_header": True, "section": True,
             "item_no": "D", "description": "WATER SPRINKLER SYSTEM",
             "unit": "", "qty": None},
            {"line_id": "bbbbbbbbbbb2", "is_header": True, "item_no": "1",
             "description": "Installation of MS pipe, ERW, heavy class",
             "unit": "", "qty": None},
            {"line_id": "bbbbbbbbbbb3", "is_header": False, "item_no": "a",
             "description": "150 mm dia", "unit": "Mtr", "qty": 120.0,
             "labour_rate": 1080.0},
            {"line_id": "bbbbbbbbbbb4", "is_header": False, "item_no": "b",
             "description": "100 mm dia (rate only)", "unit": "Mtr", "qty": 0.0,
             "labour_rate": 720.0},
            {"line_id": "bbbbbbbbbbb5", "is_header": True, "section": True,
             "item_no": "F", "description": "WATER SPRAY SYSTEM",
             "unit": "", "qty": None},
            {"line_id": "bbbbbbbbbbb6", "is_header": False, "item_no": "1",
             "description": "Deluge valve, 100 mm", "unit": "Nos", "qty": 2.0,
             "labour_rate": 9500.0},
            {"line_id": "bbbbbbbbbbb7", "is_header": False, "item_no": "2",
             "description": "Painting, two coats", "unit": "Sqm", "qty": 42.5,
             "labour_rate": 65.25},
        ],
    }
    STORE["work_orders"][GOLD_WO_BOTH] = {
        **head, "id": GOLD_WO_BOTH, "ref": "SF/WO/0003",
        "tracks": "both", "gst_rate": 18.0,
        "lines": [
            {"line_id": "ccccccccccc1", "item_no": "1", "unit": "Mtrs",
             "description": "Supply and laying of 50 NB MS pipe\nincluding clamps",
             "qty": 120.0, "material_rate": 410.0, "labour_rate": 95.5},
            {"line_id": "ccccccccccc2", "item_no": "1.a", "unit": "Nos",
             "description": "Sprinkler drop, pendent type",
             "qty": 36.0, "material_rate": 0.0, "labour_rate": 180.0},
            {"line_id": "ccccccccccc3", "item_no": "", "unit": "Sqm",
             "description": "Painting, two coats of synthetic enamel",
             "qty": 42.5, "material_rate": 65.25, "labour_rate": 0.0},
        ],
    }
    yield
    STORE["work_orders"].pop(GOLD_WO_LABOUR, None)
    STORE["work_orders"].pop(GOLD_WO_BOTH, None)


# Captured 5 October 2026 on their first render — two NEW prints; neither the
# work order's first golden above nor any in tests/test_print_golden.py moved.
WO_PASS3_GOLDENS = {
    GOLD_WO_LABOUR: ("52543d8487c5b10d", 87065),
    GOLD_WO_BOTH: ("110c01dc85774ccb", 85902),
}


@pytest.mark.parametrize("wid", [GOLD_WO_LABOUR, GOLD_WO_BOTH])
def test_the_pass_3_work_order_prints_match_their_goldens(client, golden_wo_pass3, wid):
    html = client.get(f"/wo/print/{wid}").get_data(as_text=True)
    got = (hashlib.sha256(html.encode("utf-8")).hexdigest()[:16], len(html))
    assert got == WO_PASS3_GOLDENS[wid], (
        f"the {wid} print changed: {got} against {WO_PASS3_GOLDENS[wid]}; "
        f"blocks {_blocks(html, SHEET_BLOCKS)}")


def test_the_pass_3_goldens_print_the_figures_they_describe(client, golden_wo_pass3):
    lab = client.get(f"/wo/print/{GOLD_WO_LABOUR}").get_data(as_text=True)
    # 120 x 1080 + 0 = 1,29,600 | 2 x 9500 + 42.5 x 65.25 (2,773.12) = 21,773.12.
    assert _sums(lab) == [
        ("Subtotal - WATER SPRINKLER SYSTEM", "1,29,600.00"),
        ("Subtotal - WATER SPRAY SYSTEM", "21,773.12"),
        ("WATER SPRINKLER SYSTEM", "1,29,600.00"), ("WATER SPRAY SYSTEM", "21,773.12"),
        ("Total", "1,51,373.12"), ("GST @ 18%", "27,247.16"),
        ("Total (incl. GST)", "1,78,620.28")]
    both = client.get(f"/wo/print/{GOLD_WO_BOTH}").get_data(as_text=True)
    # The first golden's figures, plus 18% on 69,913.12.
    assert _sums(both) == [
        ("Total", "17,940.00"), ("Grand Total (Material + Labour)", "69,913.12"),
        ("GST @ 18%", "12,584.36"), ("Total (incl. GST)", "82,497.48")]
