"""
An RA bill raised FROM delivery challans, or FROM the measurement — and a
billed challan, marked and blocked.

CLIENT_CHANGES.md §0, fortieth block (4 October 2026). Manas's rulings, final:

  A  RA SUPPLY from ticked challans: prefill per `line_id` = the sum across the
     ticked challans; editable DOWN, never above that sum — refused ON THE
     POST; the BOQ cumulative over-claim guard still applies on top.
  B  RA INSTALLATION from the measurement: prefill per `line_id` = measured
     less installation already claimed on non-cancelled bills, clamped at 0;
     the existing measurement cap keeps guarding the POST.
  C  A billed challan — listed in `source_dc_ids` by a NON-CANCELLED bill — is
     marked on `/dc/view` and the register, absent from the picker, and
     refused on a POST, the message naming the bill. Derived, never stored;
     ONE predicate (`dcbill.py`).

Every guard below was proved non-vacuous by MUTATION — break it, watch the
test go red, restore — and the mutations are listed in the pass's report.

The shipped configuration has the approval ladder OFF (`approval.LADDER_ON`),
so this file runs in it: a saved sheet that is not rejected counts toward the
installation ceiling. The one test that needs an UNapproved sheet turns the
ladder on for itself.
"""

import ast
import copy
import json
import pathlib
import re

import pytest

import approval
import auth
import boq as BQ
import dcbill as DCB
import demo_data as DD
import measurement as MS
import merged_ra
import ra
import settings as ST
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent


# ═══ Fixtures and builders ═════════════════════════════════════════════════

@pytest.fixture()
def seeded(client):
    """The demo schedule with nothing in front of it — no bill, no challan, no sheet."""
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    STORE.setdefault("delivery_challans", {}).clear()
    STORE.setdefault("merged_ras", {}).clear()
    BQ.ensure_demo_boq()
    yield DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE.setdefault("measurements", {}).clear()
    STORE.setdefault("delivery_challans", {}).clear()
    STORE.setdefault("merged_ras", {}).clear()


def _lines(boq_id, min_qty=10.0):
    """Priced lines with room in them — every figure below fits under the BOQ."""
    return [li for li in STORE["boqs"][boq_id]["line_items"]
            if not li["is_header"] and float(li["total_qty"] or 0) >= min_qty]


def _dc(boq_id, cid, ref, rows, date="2026-10-01"):
    """One challan. `rows` is `[(line or None, qty, line_id override)]`."""
    items = []
    for row in rows:
        line, qty = row[0], row[1]
        lid = row[2] if len(row) > 2 else line["line_id"]
        items.append({"line_id": lid, "is_header": False,
                      "item_no": (line or {}).get("item_no", "X.9"),
                      "description": (line or {}).get("description",
                                                      "Something no schedule carries"),
                      "unit": (line or {}).get("unit", "Nos"), "qty": float(qty)})
    STORE["delivery_challans"][cid] = {
        "id": cid, "ref": ref, "date": date, "boq_id": boq_id,
        "boq_ref": STORE["boqs"][boq_id].get("ref", ""),
        "boq_rev_no": STORE["boqs"][boq_id].get("rev_no", 0),
        "project_name": "P", "site_location": "", "account_name": "A",
        "consignee_id": "", "consignee_source": "typed",
        "consignee_name": "Samruddhi Fire", "consignee_addr": "",
        "consignee_phone": "", "dispatch_mode": "Transport",
        "dispatch_to": "", "po_no": "", "po_date": "", "notes": "",
        "items": items, "company_branch": "", "auth_signatory": ""}
    return cid


def _sheet(boq_id, mid, ref, rows, status=None, grid_only=False):
    """One measurement sheet. `rows` is `[(line, qty)]`; status None = undecided."""
    items = [] if grid_only else [
        {"line_id": line["line_id"], "is_header": False,
         "item_no": line["item_no"], "description": line["description"],
         "unit": line["unit"], "qty": float(qty),
         "boq_qty": float(line["total_qty"])} for line, qty in rows]
    rec = {"id": mid, "ref": ref, "fy": "26-27", "date": "2026-10-01",
           "boq_id": boq_id, "boq_ref": STORE["boqs"][boq_id].get("ref", ""),
           "boq_rev_no": 0, "items": items, "created_by": "somebody-else",
           "grid_model": MS.GRID_MODEL_JOINT,
           "grid_columns": [dict(c) for c in ST.DEFAULT_MEASUREMENT_COLUMNS],
           "grid_rows": [{"label": "H1", "values": {"d25": 12.5},
                          "remarks": "riser"}]}
    if status:
        rec["approval_status"] = status
    STORE["measurements"][mid] = rec
    return mid


def _payload(boq_id, leg, qtys):
    """The claim grid's hidden JSON for `{line_id: qty}`."""
    lines = []
    for li in STORE["boqs"][boq_id]["line_items"]:
        lid = li.get("line_id")
        if lid in qtys:
            rate = li["supply_rate"] if leg == "supply" else li["install_rate"]
            lines.append({"line_id": lid, "qty": str(qtys[lid]), "rate": str(rate)})
    for lid, q in qtys.items():                    # ids no BOQ line carries
        if not any(x["line_id"] == lid for x in lines):
            lines.append({"line_id": lid, "qty": str(q), "rate": "10"})
    return json.dumps({"lines": lines})


def _post(client, boq_id, leg, qtys, dc=None, ms=None, url=None):
    """POST the create form. Returns (response, the new bill or None)."""
    before = set(STORE["ra_bills"])
    data = {"ra_json": _payload(boq_id, leg, qtys), "date": "2026-10-04"}
    if dc is not None:
        data["dc"] = list(dc)
    if ms is not None:
        data["ms"] = ms
    r = client.post(url or f"/ra/create?boq={boq_id}&leg={leg}", data=data)
    new = set(STORE["ra_bills"]) - before
    return r, (STORE["ra_bills"][new.pop()] if new else None)


def _prefill(html, lid) -> str:
    """The value the claim grid renders in one line's quantity box."""
    m = re.search(rf'id="q_{re.escape(lid)}"\s+value="([^"]*)"', html)
    assert m, f"no quantity box for line {lid}"
    return m.group(1)


def _user(slug, role):
    auth.ensure_builtin_roles()
    existing = auth.find_user(slug)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(slug, slug.title(), f"{slug}-password", [role],
                            created_by="test")


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


# ═══ A — RA SUPPLY from ticked challans ════════════════════════════════════

def test_the_prefill_sums_each_line_across_two_ticked_challans(client, seeded):
    l1, l2, l3 = _lines(seeded)[:3]
    _dc(seeded, "dc-a", "54", [(l1, 2), (l2, 1)])
    _dc(seeded, "dc-b", "55", [(l1, 3)])

    html = client.get(f"/ra/create?boq={seeded}&leg=supply&dc=dc-a&dc=dc-b") \
                 .get_data(as_text=True)
    assert _prefill(html, l1["line_id"]) == "5", "2 + 3 across the two challans"
    assert _prefill(html, l2["line_id"]) == "1"
    assert _prefill(html, l3["line_id"]) == "", (
        "a line nothing dispatched must not be prefilled")
    # Both arrive ticked in the picker, and both ride the POST as hidden fields.
    assert html.count('name="dc" value="dc-a" checked') == 1
    assert html.count('name="dc" value="dc-b" checked') == 1
    assert '<input type="hidden" name="dc" value="dc-a"/>' in html
    assert '<input type="hidden" name="dc" value="dc-b"/>' in html


def test_coming_from_the_challan_page_the_challan_arrives_ticked(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _dc(seeded, "dc-b", "55", [(l1, 3)])
    view = client.get("/dc/view/dc-a").get_data(as_text=True)
    m = re.search(r'href="(/ra/create\?[^"]*)"[^>]*>&#43;&nbsp;Raise RA \(Supply\)', view)
    assert m, "the challan page offers no Raise RA (Supply)"
    html = client.get(m.group(1).replace("&amp;", "&")).get_data(as_text=True)
    assert 'value="dc-a" checked' in html and 'value="dc-b" checked' not in html
    assert _prefill(html, l1["line_id"]) == "2"


def test_a_quantity_above_the_ticked_challans_sum_is_refused_on_the_POST(client, seeded):
    l1, l2, l3 = _lines(seeded)[:3]
    _dc(seeded, "dc-a", "54", [(l1, 2), (l2, 1)])
    _dc(seeded, "dc-b", "55", [(l1, 3)])

    r, bill = _post(client, seeded, "supply", {l1["line_id"]: 6}, dc=["dc-a", "dc-b"])
    assert bill is None and r.status_code == 200, "6 against 5 dispatched was saved"
    assert "dispatched 5" in r.get_data(as_text=True)

    # A line no ticked challan carried has a cap of nil.
    r, bill = _post(client, seeded, "supply",
                    {l1["line_id"]: 1, l3["line_id"]: 1}, dc=["dc-a", "dc-b"])
    assert bill is None, "a line the ticked challans never carried was billed"
    assert "none of the ticked challans carried this" in r.get_data(as_text=True)

    # At the cap exactly, it saves.
    _r, bill = _post(client, seeded, "supply",
                     {l1["line_id"]: 5, l2["line_id"]: 1}, dc=["dc-a", "dc-b"])
    assert bill is not None
    assert bill[DCB.SOURCE_KEY] == ["dc-a", "dc-b"]


def test_editing_down_saves_and_the_shortfall_is_warned_not_refused(client, seeded):
    l1, l2 = _lines(seeded)[:2]
    _dc(seeded, "dc-a", "54", [(l1, 5), (l2, 1)])

    form = client.get(f"/ra/create?boq={seeded}&leg=supply&dc=dc-a").get_data(as_text=True)
    assert "Billing a" in form and "shortfall can then only go on a" in form, (
        "the warning must be on the page BEFORE save")

    r, bill = _post(client, seeded, "supply", {l1["line_id"]: 4}, dc=["dc-a"])
    assert bill is not None, "billing below dispatch is allowed"
    assert bill[DCB.SOURCE_KEY] == ["dc-a"]
    where = r.headers.get("Location", "")
    from urllib.parse import unquote_plus
    assert "2 lines were billed below" in unquote_plus(where), (
        "l1 at 4 of 5 and l2 at 0 of 1 are both short")
    assert DCB.billed_by("dc-a")[0] == bill["id"], (
        "a challan billed short still counts as billed — ruling A's own words")


def test_the_BOQ_overclaim_guard_still_runs_on_top_of_the_challan_cap(client, seeded):
    l1 = _lines(seeded)[0]
    over = float(l1["total_qty"]) + 3
    _dc(seeded, "dc-a", "54", [(l1, over)])        # over-dispatch only WARNS
    r, bill = _post(client, seeded, "supply", {l1["line_id"]: over}, dc=["dc-a"])
    assert bill is None, "a claim past the approved BOQ was saved"
    assert "over." in r.get_data(as_text=True)


def test_the_prefill_is_not_rounded_up_past_the_cap(client, seeded):
    """`_fmt_qty()` rounds to six figures (§7 gap 45); a prefill must not."""
    l1 = next(li for li in _lines(seeded, 1300.0))
    _dc(seeded, "dc-a", "54", [(l1, 1234.5678)])
    html = client.get(f"/ra/create?boq={seeded}&leg=supply&dc=dc-a").get_data(as_text=True)
    value = _prefill(html, l1["line_id"])
    assert value == "1234.5678"
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: value}, dc=["dc-a"])
    assert bill is not None, "the form's own prefill was refused by the cap"


def test_a_challan_on_another_schedule_is_refused(client, seeded):
    l1 = _lines(seeded)[0]
    other = "boq-other"
    STORE["boqs"][other] = dict(copy.deepcopy(STORE["boqs"][seeded]), id=other,
                                ref="SF/BOQ/26-27/0999", supersedes="")
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _dc(other, "dc-x", "77", [(l1, 2)])
    r, bill = _post(client, seeded, "supply", {l1["line_id"]: 1}, dc=["dc-a", "dc-x"])
    assert bill is None
    assert "Challan 77 was raised against SF/BOQ/26-27/0999" in r.get_data(as_text=True)


def test_ticking_nothing_on_the_supply_form_is_the_manual_path(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 1)])
    html = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert "Raise from delivery challans" in html, "the picker is on every supply form"
    assert 'name="dc" value="dc-a"' in html and 'value="dc-a" checked' not in html
    assert _prefill(html, l1["line_id"]) == ""
    assert '<input type="hidden" name="dc"' not in html
    assert "var DC_CAPS" not in html


# ═══ C — billed: marked, blocked, derived ══════════════════════════════════

def test_a_billed_challan_is_absent_from_the_picker_and_named_beneath_it(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _dc(seeded, "dc-b", "55", [(l1, 1)])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    assert bill is not None

    html = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert 'name="dc" value="dc-a"' not in html, "a billed challan is still pickable"
    assert 'name="dc" value="dc-b"' in html
    assert "Already billed, so not listed: 54 in" in html
    assert bill["ref"] in html


def test_a_POST_naming_a_billed_challan_is_refused_and_names_the_bill(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _r, first = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    assert first is not None

    r, second = _post(client, seeded, "supply", {l1["line_id"]: 1}, dc=["dc-a"])
    assert second is None, "the same challan was billed twice"
    body = r.get_data(as_text=True)
    assert f"Challan 54 is already billed in {first['ref']}" in body
    assert f"(RA{first['ra_no']})" in body


def test_a_GET_naming_a_billed_challan_names_the_bill_and_leaves_it_unticked(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _r, first = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    r = client.get(f"/ra/create?boq={seeded}&leg=supply&dc=dc-a")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f"already billed in {first['ref']}" in body
    assert _prefill(body, l1["line_id"]) == ""
    assert '<input type="hidden" name="dc"' not in body


def test_cancelling_the_bill_frees_the_challan_with_no_write_to_it(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    before = copy.deepcopy(STORE["delivery_challans"]["dc-a"])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    assert DCB.billed_by("dc-a")[0] == bill["id"]
    assert STORE["delivery_challans"]["dc-a"] == before, "billing wrote to the challan"

    confirm = client.get(f"/ra/cancel/{bill['id']}").get_data(as_text=True)
    assert "frees them" in confirm and "54" in confirm

    client.post(f"/ra/cancel/{bill['id']}", data={"cancel_reason": "remeasured"})
    assert ra.is_cancelled(bill)
    assert DCB.billed_by("dc-a") is None, "a cancelled bill still holds its challan"
    assert STORE["delivery_challans"]["dc-a"] == before, "freeing wrote to the challan"
    assert "Billed in" not in client.get("/dc/view/dc-a").get_data(as_text=True)
    html = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert 'name="dc" value="dc-a"' in html, "the freed challan is not pickable again"
    _r, again = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    assert again is not None and DCB.billed_by("dc-a")[0] == again["id"]


def test_deleting_a_draft_bill_frees_the_challan_too(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    client.post(f"/ra/delete/{bill['id']}")
    assert bill["id"] not in STORE["ra_bills"]
    assert DCB.billed_by("dc-a") is None


def test_a_legacy_bill_without_source_dc_ids_marks_no_challan_billed(client, seeded):
    """Absent means manual / pre-feature — a WRITTEN meaning, never inferred."""
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    STORE["ra_bills"]["legacy-1"] = {
        "id": "legacy-1", "ref": "SF/RA/26-27/0001", "fy": "26-27", "ra_no": 1,
        "date": "2026-08-06", "boq_id": seeded, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "leg": "supply", "status": "issued",
        "claims": [ra.build_claim(l1, 2.0, l1["supply_rate"], 0.0, l1["supply_rate"])],
        "claim_subtotal": 0.0, "deductions": [], "deduction_total": 0.0,
        "net_payable": 0.0, "grand_total": 0.0, "notes": ""}
    assert DCB.billing_index() == {}
    view = client.get("/dc/view/dc-a").get_data(as_text=True)
    assert "Billed in" not in view and "Raise RA (Supply)" in view
    assert "Billed in" not in client.get("/dc/").get_data(as_text=True)
    picker = client.get(f"/ra/create?boq={seeded}&leg=supply").get_data(as_text=True)
    assert 'name="dc" value="dc-a"' in picker
    assert "Raised from" not in client.get("/ra/view/legacy-1").get_data(as_text=True)


def test_the_challan_page_and_the_register_say_billed_and_link_the_bill(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _dc(seeded, "dc-b", "55", [(l1, 1)])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])

    view = client.get("/dc/view/dc-a").get_data(as_text=True)
    assert f'href="/ra/view/{bill["id"]}">{bill["ref"]}</a>' in view
    assert "Raise RA (Supply)" not in view, "a billed challan offers a second bill"
    unbilled = client.get("/dc/view/dc-b").get_data(as_text=True)
    assert "Billed in" not in unbilled and "Raise RA (Supply)" in unbilled

    register = client.get("/dc/").get_data(as_text=True)
    assert register.count("Billed in ") == 1
    assert f'href="/ra/view/{bill["id"]}"' in register

    # The delete confirmation names the bill too — a warning, not a refusal.
    assert bill["ref"] in client.get("/dc/delete/dc-a").get_data(as_text=True)


def test_the_billed_predicate_agrees_with_ra_is_cancelled_on_every_status():
    """`dcbill` may not import `ra`, so it tests the raw field; the two agree."""
    for status in ("draft", "issued", "cancelled", "CANCELLED", " cancelled ",
                   "Cancelled", "submitted", "certified", "", None, "void",
                   "draft ", "ISSUED"):
        bill = {"status": status}
        assert DCB.bill_is_live(bill) == (not ra.is_cancelled(bill)), status
    assert DCB.bill_is_live({}) == (not ra.is_cancelled({}))


def test_there_is_one_billed_predicate_and_both_pages_read_it():
    """
    ABOUT.md §7 gap 16b's failure is two near-identical predicates in two
    modules. Only `dcbill.py` may spell the key; `ra.py` and `challan.py`
    reach the answer through it.
    """
    # Read from the AST: a comment or a docstring may name the key, and only a
    # live string constant equal to it can read a bill's field.
    spelling = sorted(
        p.name for p in REPO.glob("*.py")
        if any(isinstance(n, ast.Constant) and n.value == "source_dc_ids"
               for n in ast.walk(ast.parse(p.read_text(encoding="utf8")))))
    assert spelling == ["dcbill.py"], (
        f"the billed key is spelled outside the leaf: {spelling}")
    for mod in ("ra.py", "challan.py"):
        src = (REPO / mod).read_text(encoding="utf8")
        assert "DCB.billed_by(" in src or "DCB.billing_index(" in src, mod
    # challan.py may not grow its own reading of a bill: it never names the
    # bills collection or a bill's status at all.
    challan_src = (REPO / "challan.py").read_text(encoding="utf8")
    assert "ra_bills" not in challan_src and "cancelled" not in challan_src


# ═══ The manual path — exactly as today, exposure and all ══════════════════

def test_the_manual_path_writes_no_source_key_and_carries_no_challan_cap(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 1)])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 7})   # above dispatch
    assert bill is not None, "the manual path gained a challan cap"
    assert DCB.SOURCE_KEY not in bill and ra.SOURCE_MS_KEY not in bill, (
        "absent is the written meaning of manual — no key, not an empty list")
    assert DCB.billed_by("dc-a") is None


def test_the_manual_path_can_still_rebill_a_billed_challans_quantity(client, seeded):
    """
    ⚠ **PINNED AS THE CURRENT BEHAVIOUR, NOT ENDORSED.** The brief says the
    manual path keeps working exactly as today and does NOT get the challan
    lock, and asks for the exposure to be REPORTED. So a manual bill may claim
    the very quantity a challan was already billed for, limited only by the
    BOQ cumulative cap. If the lock is ever extended to the manual path, this
    test is the one that should be rewritten — deliberately.
    """
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _r, from_dc = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    _r, manual = _post(client, seeded, "supply", {l1["line_id"]: 2})
    assert from_dc is not None and manual is not None
    assert DCB.billed_by("dc-a")[0] == from_dc["id"]


def test_the_manual_installation_form_is_untouched(client, seeded):
    l1 = _lines(seeded)[0]
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 4)])
    html = client.get(f"/ra/create?boq={seeded}&leg=installation").get_data(as_text=True)
    assert _prefill(html, l1["line_id"]) == ""
    assert "Prefilled from the" not in html and 'name="ms"' not in html
    assert "Raise from delivery challans" not in html
    _r, bill = _post(client, seeded, "installation", {l1["line_id"]: 1})
    assert bill is not None and ra.SOURCE_MS_KEY not in bill


# ═══ Matching on line_id ONLY ═══════════════════════════════════════════════

def test_unmatched_rows_are_listed_and_never_prefilled_or_billed(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2), (None, 3, "0123456789ab"), (None, 1, "")])
    html = client.get(f"/ra/create?boq={seeded}&leg=supply&dc=dc-a").get_data(as_text=True)
    assert "Unmatched, not prefilled" in html
    assert html.count("Something no schedule carries") == 2
    assert _prefill(html, l1["line_id"]) == "2"
    assert 'id="q_0123456789ab"' not in html
    r, bill = _post(client, seeded, "supply",
                    {l1["line_id"]: 1, "0123456789ab": 1}, dc=["dc-a"])
    assert bill is None, "a line not on the schedule was billed through this path"
    assert "not in the approved BOQ" in r.get_data(as_text=True)


def test_a_challan_on_a_superseded_revision_matches_by_line_id_only(client, seeded):
    """A line the revision deleted is unmatched; a surviving line still matches."""
    keep, gone = _lines(seeded)[:2]
    _dc(seeded, "dc-old", "50", [(keep, 2), (gone, 1)])
    rev = "boq-rev-1"
    STORE["boqs"][rev] = dict(copy.deepcopy(STORE["boqs"][seeded]), id=rev,
                              rev_no=1, supersedes=seeded)
    STORE["boqs"][rev]["line_items"] = [
        li for li in STORE["boqs"][rev]["line_items"]
        if li.get("line_id") != gone["line_id"]]

    # The challan names its OWN revision; the button resolves the TIP.
    html = client.get("/ra/create?leg=supply&dc=dc-old").get_data(as_text=True)
    assert "&middot; rev 1</span>" in html, "the bill must be raised against the tip"
    assert _prefill(html, keep["line_id"]) == "2", "a surviving line_id still matches"
    assert "Unmatched, not prefilled" in html
    assert gone["description"].split()[0] in html
    r, bill = _post(client, rev, "supply", {keep["line_id"]: 2, gone["line_id"]: 1},
                    dc=["dc-old"])
    assert bill is None
    _r, bill = _post(client, rev, "supply", {keep["line_id"]: 2}, dc=["dc-old"])
    assert bill is not None and bill["boq_id"] == rev


# ═══ B — RA INSTALLATION from the measurement ══════════════════════════════

def test_the_installation_prefill_is_the_unbilled_remainder_after_a_first_bill(client, seeded):
    l1, l2 = _lines(seeded)[:2]
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 10), (l2, 5)])
    _r, first = _post(client, seeded, "installation", {l1["line_id"]: 4})
    assert first is not None

    html = client.get("/ra/create?leg=installation&ms=ms-a").get_data(as_text=True)
    assert "&middot; installation</span>" in html, "ms= implies the installation leg"
    assert _prefill(html, l1["line_id"]) == "6", "10 measured less 4 claimed"
    assert _prefill(html, l2["line_id"]) == "5"
    assert "Prefilled from the" in html and "SF/MS/26-27/0001" in html


def test_the_remainder_clamps_at_nil_and_ignores_a_cancelled_bill(client, seeded):
    l1, l2, l3 = _lines(seeded)[:3]
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 4), (l2, 3), (l3, 2)])
    _r, full = _post(client, seeded, "installation", {l1["line_id"]: 4})
    _r, void = _post(client, seeded, "installation", {l2["line_id"]: 3})
    client.post(f"/ra/cancel/{void['id']}", data={"cancel_reason": "withdrawn"})
    # A bill the cap grandfathered may stand above the measurement.
    STORE["ra_bills"]["over-1"] = dict(copy.deepcopy(full), id="over-1", ra_no=99,
                                       status="issued")
    STORE["ra_bills"]["over-1"]["claims"] = [
        ra.build_claim(l3, 5.0, 1.0, 0.0, 1.0, leg="installation")]

    rem = ra.unbilled_remainder(seeded)
    assert l1["line_id"] not in rem, "a fully claimed line must not be prefilled"
    assert rem.get(l2["line_id"]) == 3, "a cancelled bill releases its quantity"
    assert l3["line_id"] not in rem, "claimed past the measurement — clamped, not negative"
    html = client.get(f"/ra/create?boq={seeded}&leg=installation&ms=ms-a") \
                 .get_data(as_text=True)
    assert _prefill(html, l1["line_id"]) == ""
    assert _prefill(html, l3["line_id"]) == ""
    assert _prefill(html, l2["line_id"]) == "3"


def test_the_measurement_cap_still_guards_the_POST_and_the_source_is_written(client, seeded):
    l1 = _lines(seeded)[0]
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 6)])
    _sheet(seeded, "ms-b", "SF/MS/26-27/0002", [(l1, 2)])
    r, bill = _post(client, seeded, "installation", {l1["line_id"]: 9}, ms="ms-a")
    assert bill is None, "a claim above the measurement was saved"
    assert "over the measurement" in r.get_data(as_text=True)
    _r, bill = _post(client, seeded, "installation", {l1["line_id"]: 8}, ms="ms-a")
    assert bill is not None
    assert bill[ra.SOURCE_MS_KEY] == ["ms-a", "ms-b"], (
        "every sheet that counted toward the remainder, oldest first")
    assert DCB.SOURCE_KEY not in bill


def test_a_joint_sheet_with_a_grid_but_no_lines_prefills_nothing_and_says_so(client, seeded):
    l1 = _lines(seeded)[0]
    _sheet(seeded, "ms-lines", "SF/MS/26-27/0001", [(l1, 3)])
    _sheet(seeded, "ms-grid", "SF/MS/26-27/0002", [], grid_only=True)
    html = client.get(f"/ra/create?boq={seeded}&leg=installation&ms=ms-grid") \
                 .get_data(as_text=True)
    assert "SF/MS/26-27/0002</b> carries a joint measurement grid but no BOQ lines" in html
    assert _prefill(html, l1["line_id"]) == "3", "only the lined sheet feeds the prefill"


def test_a_sheet_that_does_not_count_is_refused(client, seeded, ladder_on):
    l1 = _lines(seeded)[0]
    _sheet(seeded, "ms-ok", "SF/MS/26-27/0001", [(l1, 3)], status=approval.APPROVED)
    _sheet(seeded, "ms-wait", "SF/MS/26-27/0002", [(l1, 1)])
    _sheet(seeded, "ms-no", "SF/MS/26-27/0003", [(l1, 1)], status=approval.REJECTED)
    r = client.get(f"/ra/create?boq={seeded}&leg=installation&ms=ms-wait")
    assert r.status_code in (302, 303)
    from urllib.parse import unquote_plus
    assert "has not been approved" in unquote_plus(r.headers["Location"])
    r = client.get(f"/ra/create?boq={seeded}&leg=installation&ms=ms-no")
    assert "was rejected" in unquote_plus(r.headers["Location"])
    assert client.get(f"/ra/create?boq={seeded}&leg=installation&ms=ms-ok").status_code == 200


# ═══ The two buttons — drawn only for somebody who may raise a bill ════════

def test_the_raise_buttons_are_drawn_only_for_a_user_who_may_raise_a_bill(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 3)])

    assert "Raise RA (Supply)" in client.get("/dc/view/dc-a").get_data(as_text=True)
    assert "Raise RA (Installation)" in client.get("/measurement/view/ms-a") \
                                              .get_data(as_text=True)

    # Purchase Manager: dc.view, no ra.create.
    _as(client, _user("pm-src", "role-purchase-manager"))
    r = client.get("/dc/view/dc-a")
    assert r.status_code == 200 and "Raise RA (Supply)" not in r.get_data(as_text=True)
    # Accountant: measurement.view, no ra.create.
    _as(client, _user("acct-src", "role-accountant"))
    r = client.get("/measurement/view/ms-a")
    assert r.status_code == 200
    assert "Raise RA (Installation)" not in r.get_data(as_text=True)
    # …and the gate agrees with what was drawn.
    assert not auth.can_reach("ra.create_ra", auth.find_user("acct-src"))


def test_a_rejected_sheet_offers_no_raise_button(client, seeded):
    l1 = _lines(seeded)[0]
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 3)])
    _sheet(seeded, "ms-no", "SF/MS/26-27/0002", [(l1, 1)], status=approval.REJECTED)
    assert "Raise RA (Installation)" not in client.get("/measurement/view/ms-no") \
                                                  .get_data(as_text=True)


# ═══ Edit, view, print ══════════════════════════════════════════════════════

def test_editing_a_bill_raised_from_challans_keeps_its_cap_and_its_source(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 5)])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    edit = client.get(f"/ra/edit/{bill['id']}").get_data(as_text=True)
    assert "Raised from delivery challans" in edit and "var DC_CAPS" in edit

    data = {"ra_json": _payload(seeded, "supply", {l1["line_id"]: 6}),
            "date": "2026-10-04"}
    r = client.post(f"/ra/edit/{bill['id']}", data=data)
    assert r.status_code == 200 and "dispatched 5" in r.get_data(as_text=True)
    assert bill["claims"][0]["qty"] == 2, "an over-cap edit moved the claim"

    data["ra_json"] = _payload(seeded, "supply", {l1["line_id"]: 5})
    client.post(f"/ra/edit/{bill['id']}", data=data)
    assert bill["claims"][0]["qty"] == 5
    assert bill[DCB.SOURCE_KEY] == ["dc-a"], "edit rewrote the write-once source"


def test_the_bill_view_names_its_source_and_a_manual_bill_names_none(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 3)])
    _r, from_dc = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    _r, from_ms = _post(client, seeded, "installation", {l1["line_id"]: 1}, ms="ms-a")
    _r, manual = _post(client, seeded, "installation", {l1["line_id"]: 1})

    v = client.get(f"/ra/view/{from_dc['id']}").get_data(as_text=True)
    assert 'Raised from delivery challans</b> <a href="/dc/view/dc-a">54</a>' in v
    v = client.get(f"/ra/view/{from_ms['id']}").get_data(as_text=True)
    assert '<a href="/measurement/view/ms-a">SF/MS/26-27/0001</a>' in v
    assert "Raised from" not in client.get(f"/ra/view/{manual['id']}").get_data(as_text=True)

    del STORE["delivery_challans"]["dc-a"]
    v = client.get(f"/ra/view/{from_dc['id']}").get_data(as_text=True)
    assert "a challan since deleted" in v


def test_printing_a_bill_raised_from_challans_reads_no_challan(client, seeded):
    """The snapshot rule: the bill's own claim rows are the source of truth."""
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    first = client.get(f"/ra/print/{bill['id']}").get_data(as_text=True)
    STORE["delivery_challans"]["dc-a"]["ref"] = "9999"
    STORE["delivery_challans"]["dc-a"]["items"][0]["qty"] = 77.0
    assert client.get(f"/ra/print/{bill['id']}").get_data(as_text=True) == first
    del STORE["delivery_challans"]["dc-a"]
    assert client.get(f"/ra/print/{bill['id']}").get_data(as_text=True) == first


# ═══ C3 — the merged RA ═════════════════════════════════════════════════════

def test_a_challan_sourced_supply_bill_merges_with_a_measured_installation_bill(client, seeded):
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54", [(l1, 2)])
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001", [(l1, 3)])
    _r, sup = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    _r, ins = _post(client, seeded, "installation", {l1["line_id"]: 3}, ms="ms-a")
    for b in (sup, ins):
        client.post(f"/ra/issue/{b['id']}", data={"issued_on": "2026-10-04"})
        assert ra.is_issued(b)

    doc, err = merged_ra.create(sup, ins, notes="from challan and sheet")
    assert doc is not None, err
    assert sup[DCB.SOURCE_KEY] == ["dc-a"] and ins[ra.SOURCE_MS_KEY] == ["ms-a"], (
        "merging must leave the source ids on the leg bills")
    assert "claims" not in doc and DCB.SOURCE_KEY not in doc
    assert client.get(f"/merged/print/{doc['id']}").status_code == 200
    assert client.get(f"/merged/view/{doc['id']}").status_code == 200
    # A merged leg cannot be cancelled, so its challan stays billed.
    client.post(f"/ra/cancel/{sup['id']}", data={"cancel_reason": "try"})
    assert not ra.is_cancelled(sup) and DCB.billed_by("dc-a")[0] == sup["id"]


# ═══ The new states, escaped and reachable ══════════════════════════════════

PAYLOAD = "SRCPROBE<script>alert(1)</script>\"'&"


def test_the_new_form_states_escape_every_record_field(client, seeded):
    """A focused sweep of what only these states render; the shared sweep in
    `test_escaping.py` walks them too, through `test_entity_fallbacks`'s
    `extra` URLs."""
    l1 = _lines(seeded)[0]
    _dc(seeded, "dc-a", "54" + PAYLOAD, [(l1, 2)])
    _dc(seeded, "dc-b", "55" + PAYLOAD, [(l1, 1), (None, 1, "0123456789ab")])
    STORE["delivery_challans"]["dc-b"]["items"][1]["description"] += PAYLOAD
    STORE["delivery_challans"]["dc-b"]["items"][1]["item_no"] += PAYLOAD
    STORE["delivery_challans"]["dc-b"]["dispatch_to"] = "Site" + PAYLOAD
    _r, bill = _post(client, seeded, "supply", {l1["line_id"]: 2}, dc=["dc-a"])
    bill["ref"] = bill["ref"] + PAYLOAD
    _sheet(seeded, "ms-a", "SF/MS/26-27/0001" + PAYLOAD, [(l1, 3)])
    _sheet(seeded, "ms-g", "SF/MS/26-27/0002" + PAYLOAD, [], grid_only=True)
    l1["item_no"] = str(l1["item_no"]) + "</script>"

    pages = [f"/ra/create?boq={seeded}&leg=supply&dc=dc-b&dc=dc-a",
             f"/ra/create?boq={seeded}&leg=installation&ms=ms-g",
             f"/ra/view/{bill['id']}", f"/ra/edit/{bill['id']}",
             f"/ra/cancel/{bill['id']}", "/dc/view/dc-a", "/dc/", "/dc/delete/dc-a"]
    carried = 0
    for url in pages:
        body = client.get(url).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in body, url
        assert "</script>\"" not in body and "'</script>" not in body, url
        carried += "SRCPROBE&lt;script&gt;" in body
    assert carried == len(pages), "a page did not carry the payload at all"


import test_escaping as ES  # noqa: E402  (the shared sweep's own fixtures)

hostile = ES.hostile
populated = ES.populated
populated_store = ES.populated_store


@pytest.fixture()
def unpoisoned_afterwards():
    """
    Put every collection the hostile fixture poisons back as it was.

    ⚠ **`test_escaping.hostile` restores the letterhead and nothing else**, and
    `conftest._fresh_store()` does not clear `settings`, `addresses` or
    `products` — so the payload it appends stays in them for every test that
    runs after. Inside `test_escaping.py` that is harmless only because of where
    the file sorts. Reused here it is not: measured on 4 October 2026, a
    poisoned challan-series number reached
    `tests/test_seed_demo_scenario.py`, whose `/settings/` GET then failed to
    parse it. Requested BEFORE `hostile`, so it is torn down after it.
    """
    saved = {name: copy.deepcopy(dict(STORE.get(name) or {}))
             for name in ES.POISONED_COLLECTIONS}
    yield
    for name, rows in saved.items():
        STORE.setdefault(name, {}).clear()
        STORE[name].update(rows)


@pytest.mark.usefixtures("catalogue_unhidden", "ladder_on")
def test_the_shared_sweep_really_renders_the_new_branches(unpoisoned_afterwards,
                                                          hostile, client):
    """
    The control for `test_escaping.py`'s sweep over the new states. Its
    assertions are "the raw payload is NOT here", which pass just as well
    against a page that never reached the branch — so this proves each new
    sink is on its page, carrying the payload, escaped.
    """
    from test_escaping import ESCAPED
    bid = DD.BOQ_META["id"]
    r2 = STORE["ra_bills"]["r2-supply"]
    expect = {
        f"/ra/create?boq={bid}&leg=supply&dc=dc-2&dc=dc-1": [
            "Raise from delivery challans", "Unmatched, not prefilled",
            "A row no line of the schedule carries" + ESCAPED,
            "Whitefield site store" + ESCAPED,
            "already billed in " + r2["ref"].replace(ES.PAYLOAD, ESCAPED)],
        f"/ra/create?boq={bid}&leg=installation&ms=ms-2": [
            "Prefilled from the", "SF/MS/26-27/0002" + ESCAPED],
        "/dc/view/dc-1": ["Billed in", "SF/RA/26-27/0002" + ESCAPED],
        "/dc/": ["Billed in SF/RA/26-27/0002" + ESCAPED],
        "/ra/view/r2-supply": ["Raised from delivery challans", "54" + ESCAPED],
        "/ra/edit/r2-supply": ["Raised from delivery challans", "var DC_CAPS"],
        "/ra/cancel/r2-supply": ["frees them", "54" + ESCAPED],
        "/dc/view/dc-2": ["Raise RA (Supply)"],
    }
    # The sweep walks every one of these — the three query-string states
    # through the fixture's `extra`, the rest through their `url_map` rules.
    for url in expect:
        assert url in hostile["urls"], f"the shared sweep never visits {url}"
    for url, needles in expect.items():
        r = client.get(url)
        assert r.status_code == 200, url
        body = r.get_data(as_text=True)
        for needle in needles:
            assert needle in body, f"{url} does not carry {needle[:60]!r}"
    edit = client.get("/ra/edit/r2-supply").get_data(as_text=True)
    assert "\\u003cscript\\u003e" in edit, (
        "the item labels in the live warning are not reaching the page escaped "
        "for a <script> block")


def test_the_new_states_are_reachable_from_the_pages_they_belong_to():
    """
    `tests/test_page_reachability.py` walks endpoints, and `/ra/create` was
    reachable before. What is new is the way in from a challan and from a
    sheet, so the link graph must carry both edges.
    """
    import test_page_reachability as PR
    precise, module_wide, _computed = PR._link_edges()
    for mod in ("challan", "measurement"):
        reach = set(module_wide.get(mod, ())) | {
            t for ep, ts in precise.items() if ep.startswith(mod + ".") for t in ts}
        assert "ra.create_ra" in reach, f"{mod}.py draws no link to /ra/create"
    src = (REPO / "ra.py").read_text(encoding="utf8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "_source_band_html")
    literals = {c.value for c in ast.walk(fn) if isinstance(c, ast.Constant)}
    assert {"challan.view_dc", "measurement.view_ms"} <= literals, (
        "the bill view must link back to the challan and the sheet")


def test_a_missing_origin_is_refused_by_name(client, seeded):
    from urllib.parse import unquote_plus
    r = client.get("/ra/create?leg=supply&dc=no-such-challan")
    assert "That challan no longer exists." in unquote_plus(r.headers["Location"])
    r = client.get("/ra/create?ms=no-such-sheet")
    assert "That measurement sheet no longer exists." in unquote_plus(r.headers["Location"])
