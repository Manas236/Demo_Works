"""
The BOQ RATE BASIS — Supply / Installation / Supply + Installation (SITC)
(21 November 2026, CLIENT_CHANGES.md §0 eighty-third block, prod hotfix).

`rate_basis` on a BOQ is one of `split` (the default, and what an absent key
reads as), `supply_only`, `installation_only`, `sitc`. An SITC rate is ONE
combined rate stored on the SUPPLY track with installation blank; it prints as
one "Supply + Installation (SITC)" column pair and RA bills it on the supply
leg. Held here:

* the import's "Rate in this sheet is for" → track and basis, per option, the
  cost switch inside the chosen track, the choice required on the page, a
  marker-less POST reading exactly as before;
* the invariant — a basis that would hide a non-zero rate is refused, naming
  the items, and nothing is zeroed;
* a revision carries the basis forward;
* the print — SITC one pair, totals foot; single-track bases; `split`
  byte-identical whether the key is absent or written;
* RA — an SITC line on the supply leg at its full rate, absent from
  installation; the "Supply (SITC)" label;
* the change through `/boq/edit` — GET writes nothing, POST is gated by
  `boq.create`, changes no amount, and is logged with who and when.

Every workbook is built in memory; no client data appears here.
"""

import copy
import json
import re

import pytest

import auth
import boq as BQ
import boqimport
import conftest
import ra
import sheetimport as SI
from store import STORE


# ── helpers ──────────────────────────────────────────────────────────────────

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
    return {"sections": [{"code": "A", "title": "Pumps", "areas": []}], "lines": list(lines)}


def save(client, model, **form):
    data = {"date": "2026-11-21", "project_name": "P", "account_name": "A",
            "boq_json": json.dumps(model)}
    data.update(form)
    before = set(STORE["boqs"])
    r = client.post("/boq/create", data=data)
    new = set(STORE["boqs"]) - before
    if r.status_code == 302 and new:
        return STORE["boqs"][new.pop()]
    return r.get_data(as_text=True)


def sitc_boq(client):
    return save(client, one_section(
        a_line(item_no="1", description="Fire pump", unit="Nos", total_qty="2",
               supply_rate="841920"),
        a_line(item_no="2", description="Gauge", unit="Nos", total_qty="10",
               supply_rate="1800")), rate_basis="sitc")


SHEET = [["Sr. No.", "Item Description", "Qty.", "Unit", "SITC Rate", "Amount"],
         [1, "Supply, installation, testing and commissioning of a pump", 2, "Nos",
          1000, 2000],
         [2, "Gauge", 10, "Nos", 50, 500]]


def stage(rows=SHEET, name="sheet.xlsx"):
    wb = SI.from_rows([("Quotation", "visible", rows)])
    return boqimport.stage(wb, name, conftest.ensure_test_user()["id"])


def preview_form(html):
    form = {"picker": "1", "tab": re.findall(
        r'<input type="checkbox" name="tab" value="(\d+)" checked', html)}
    for name, opts in re.findall(r'<select name="(map_\d+_\d+)"[^>]*>(.*?)</select>', html, re.S):
        m = re.search(r'<option value="([^"]*)" selected>', opts)
        form[name] = m.group(1) if m else ""
    for name in re.findall(r'<input type="checkbox" name="(use_\d+_\d+)" value="1" checked', html):
        form[name] = "1"
    form["project_name"], form["account_name"] = "P", "A"
    form["rate_mode"] = "selling"
    return form


def import_to_form(client, rate_for, offered=True, **changes):
    """Stage SHEET, post the preview as rendered with `rate_for`, and return
    (response, page html or None)."""
    tok, _known = stage(changes.pop("rows", SHEET))
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    form = preview_form(html)
    if offered:
        form["rate_for_offered"] = "1"
        form["rate_for"] = rate_for
    form.update(changes)
    form["action"] = "confirm"
    r = client.post(f"/boq/import/{tok}", data=form)
    if r.status_code != 303:
        return r, None
    return r, client.get(r.headers["Location"]).get_data(as_text=True)


def model_of(html):
    m = re.search(r"var MODEL = (\{.*?\});\nvar SPECS", html, re.S)
    assert m, "the page carries no editor model"
    return json.loads(m.group(1))


def selected_basis(html):
    m = re.search(r'<select id="rate_basis" name="rate_basis">(.*?)</select>', html, re.S)
    assert m, "the form draws no Rate basis select"
    sel = re.search(r'<option value="(\w+)" selected>', m.group(1))
    return sel.group(1) if sel else None


def priced(model):
    return [l for l in model["lines"] if not l["is_header"]]


# ═══ 1. The record: default, helpers ═════════════════════════════════════════

def test_a_missing_basis_reads_as_split_and_nothing_backfills_it(client):
    client.get("/boq/")
    for b in STORE["boqs"].values():
        assert BQ.rate_basis_of(b) == "split"
    seeded = [b for b in STORE["boqs"].values() if BQ.RATE_BASIS_KEY not in b]
    assert seeded, "the demo BOQ carries no key — and must keep carrying none"
    client.get(f"/boq/view/{seeded[0]['id']}")
    client.get(f"/boq/print/{seeded[0]['id']}")
    assert BQ.RATE_BASIS_KEY not in seeded[0]
    assert BQ.rate_basis_of({"rate_basis": "nonsense"}) == "split"


def test_a_new_boq_stores_the_basis_posted_and_split_without_one(client):
    rec = sitc_boq(client)
    assert rec["rate_basis"] == "sitc"
    plain = save(client, one_section(a_line()))
    assert plain["rate_basis"] == "split"


# ═══ 2. Import — "Rate in this sheet is for" ═════════════════════════════════

def test_the_preview_draws_the_required_select_and_the_sitc_hint(client):
    tok, _ = stage()
    html = client.get(f"/boq/import/{tok}").get_data(as_text=True)
    assert "Rate in this sheet is for" in html
    assert 'name="rate_for_offered" value="1"' in html
    sel = re.search(r'<select id="rate_for" name="rate_for">(.*?)</select>', html, re.S).group(1)
    assert '<option value="" selected>' in sel, "nothing is pre-selected from a guess"
    for k in ("supply", "installation", "sitc", "split"):
        assert f'<option value="{k}">' in sel
    assert "The heading says &ldquo;SITC Rate&rdquo;" in html


def test_confirm_without_a_choice_is_refused_on_the_page(client):
    r, page = import_to_form(client, "")
    assert page is None and r.status_code == 200
    assert "Choose what the rate in this sheet is for" in r.get_data(as_text=True)


@pytest.mark.parametrize("rate_for,basis,on_supply", [
    ("supply", "supply_only", True),
    ("sitc", "sitc", True),
    ("installation", "installation_only", False),
    ("split", "split", True),
])
def test_each_option_puts_the_rate_on_its_track_and_sets_the_basis(
        client, rate_for, basis, on_supply):
    _r, page = import_to_form(client, rate_for)
    assert page is not None
    lines = priced(model_of(page))
    assert [l["item_no"] for l in lines] == ["1", "2"]
    for l, want in zip(lines, ("1000", "50")):
        if on_supply:
            assert (l["supply_rate"], l["install_rate"]) == (want, "")
        else:
            assert (l["supply_rate"], l["install_rate"]) == ("", want)
    assert selected_basis(page) == basis
    # Saving the prefilled form stores that basis and the rates as they came.
    rec = save(client, model_of(page), rate_basis=selected_basis(page))
    assert isinstance(rec, dict), rec[:2000]
    assert rec["rate_basis"] == basis
    li = rec["line_items"][0]
    assert (li["supply_rate"], li["install_rate"]) == ((1000.0, None) if on_supply
                                                       else (None, 1000.0))
    assert li["description"] == SHEET[1][1], "names come over word for word"


def test_a_post_without_the_select_reads_exactly_as_before(client):
    _r, page = import_to_form(client, None, offered=False)
    assert page is not None
    lines = priced(model_of(page))
    assert lines[0]["supply_rate"] == "1000" and lines[0]["install_rate"] == ""
    assert selected_basis(page) == "split"


def test_the_cost_switch_works_inside_the_installation_track(client):
    _r, page = import_to_form(client, "installation", rate_mode="cost", markup="10")
    assert page is not None
    l = priced(model_of(page))[0]
    assert l["install_base_rate"] == "1000" and l["install_escalation_pct"] == "10"
    assert l["install_rate"] == "" and l["_cost"] == ["install"]
    assert l["supply_base_rate"] == "" and l["supply_rate"] == ""


def test_the_cost_switch_works_inside_the_sitc_track(client):
    _r, page = import_to_form(client, "sitc", rate_mode="cost", markup="10")
    l = priced(model_of(page))[0]
    assert l["supply_base_rate"] == "1000" and l["supply_escalation_pct"] == "10"
    assert l["install_base_rate"] == "" and l["_cost"] == ["supply"]


def test_sitc_with_an_installation_column_ticked_is_refused_naming_it(client):
    rows = [["Sr. No.", "Description", "Qty", "Unit", "Supply Rate", "Installation Rate"],
            [1, "Pipe", 2, "Nos", 100, 40]]
    r, page = import_to_form(client, "sitc", rows=rows)
    assert page is None
    body = r.get_data(as_text=True)
    assert "an Installation column is ticked: column F (Installation · unit rate)" in body
    _r, ok = import_to_form(client, "split", rows=rows)
    l = priced(model_of(ok))[0]
    assert (l["supply_rate"], l["install_rate"]) == ("100", "40")


def test_the_choice_is_remembered_with_the_layout(client):
    _r, page = import_to_form(client, "sitc")
    assert page is not None
    tok, known = stage()
    assert known, "a layout confirmed with a choice goes straight to the form"
    html = client.get(f"/boq/import/{tok}/form").get_data(as_text=True)
    assert selected_basis(html) == "sitc"
    assert "Supply + Installation (SITC)" in html


def test_a_layout_remembered_before_the_question_stops_at_the_preview(client):
    _r, page = import_to_form(client, "split")
    for lay in STORE["import_layouts"].values():
        lay.pop("rate_for", None)                    # a layout saved before today
    _tok, known = stage()
    assert not known


# ═══ 3. The invariant ════════════════════════════════════════════════════════

@pytest.mark.parametrize("basis", ["sitc", "supply_only"])
def test_sitc_or_supply_only_is_refused_with_an_installation_rate(client, basis):
    before = copy.deepcopy(STORE["boqs"])
    body = save(client, one_section(
        a_line(item_no="1", supply_rate="100"),
        a_line(item_no="2", supply_rate="100", install_rate="40"),
        a_line(item_no="3", supply_rate="", install_base_rate="30")), rate_basis=basis)
    assert isinstance(body, str)
    assert "cannot be saved: 2 lines carry an installation rate" in body
    assert "items A 2, A 3" in body
    assert STORE["boqs"] == before, "nothing saved"
    back = model_of(body)["lines"]
    assert back[1]["install_rate"] == "40" and back[2]["install_base_rate"] == "30", \
        "the refused page keeps every rate as typed — nothing is zeroed"


def test_installation_only_is_refused_with_a_supply_rate(client):
    body = save(client, one_section(a_line(item_no="7", supply_rate="100", install_rate="5")),
                rate_basis="installation_only")
    assert isinstance(body, str)
    assert "1 line carries a supply rate" in body and "item A 7" in body


def test_a_zero_rate_on_the_hidden_track_is_not_a_rate(client):
    rec = save(client, one_section(a_line(supply_rate="100", install_rate="0")),
               rate_basis="sitc")
    assert isinstance(rec, dict) and rec["rate_basis"] == "sitc"


# ═══ 4. Revisions ════════════════════════════════════════════════════════════

def test_a_revision_carries_the_basis_forward(client):
    rec = sitc_boq(client)
    html = client.get(f"/boq/create?revise={rec['id']}").get_data(as_text=True)
    assert selected_basis(html) == "sitc"
    boot, _pf = BQ._form_payload_from(rec)
    # Posted WITHOUT a basis (an older page): the predecessor's is carried.
    r = client.post("/boq/create", data={
        "date": "2026-11-21", "project_name": "P", "account_name": "A",
        "rev_no": "1", "supersedes": rec["id"], "boq_json": json.dumps(boot)})
    assert r.status_code == 302
    rev = [b for b in STORE["boqs"].values() if b.get("supersedes") == rec["id"]][0]
    assert rev["rate_basis"] == "sitc"
    assert rev["ref"] == rec["ref"] + "/1", "the /N revision scheme is untouched"


# ═══ 5. The print ════════════════════════════════════════════════════════════

def _grid_ok(html):
    """Every section table's rows occupy exactly its colgroup (rowspan aware)."""
    for t in re.findall(r'<table class="boq-table">(.*?)</table>', html, re.S):
        ncol = len(re.findall(r"<col ", t))
        carry = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
            w = sum(1 for c in carry if c > 0)
            carry = [c - 1 for c in carry if c > 1]
            for tag in re.findall(r"<t[hd][^>]*>", tr):
                cs = re.search(r'colspan="(\d+)"', tag)
                rs = re.search(r'rowspan="(\d+)"', tag)
                n = int(cs.group(1)) if cs else 1
                w += n
                if rs:
                    carry += [int(rs.group(1)) - 1] * n
            assert w == ncol, (w, ncol, tr[:200])
    return True


def test_the_sitc_print_has_one_combined_pair_and_its_totals_foot(client):
    rec = sitc_boq(client)
    html = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
    assert "Supply + Installation (SITC)<br/>U/ Rate" in html
    assert "Amount (SITC)" in html
    assert "Installation<br/>U/ Rate" not in html
    assert "Installation Amount" not in html
    assert "Supply Amount" not in html
    assert _grid_ok(html)
    total = 2 * 841920 + 10 * 1800                      # 17,01,840
    sub = re.search(r"BASIC VALUE SUBTOTAL \(A\).*?</tr>", html, re.S).group(0)
    assert "17,01,840.00" in sub
    grand = re.search(r'<div class="boq-grand">.*?</table>', html, re.S).group(0)
    assert '<td class="bg-tag">Supply + Installation (SITC)</td>' in grand
    assert '<td class="bg-tag">Installation</td>' not in grand
    assert grand.count("17,01,840.00") == 2              # the track and the basic value
    assert rec["subtotal"] == total


def test_the_sitc_view_hides_installation_too_and_keeps_the_breakup(client):
    rec = sitc_boq(client)
    html = client.get(f"/boq/view/{rec['id']}").get_data(as_text=True)
    assert "Installation Amount" not in html and _grid_ok(html)


@pytest.mark.parametrize("basis,shown,hidden", [
    ("supply_only", "Supply<br/>U/ Rate", "Installation<br/>U/ Rate"),
    ("installation_only", "Installation<br/>U/ Rate", "Supply<br/>U/ Rate"),
])
def test_a_single_track_basis_prints_only_that_track(client, basis, shown, hidden):
    line = (a_line(supply_rate="100") if basis == "supply_only"
            else a_line(supply_rate="", install_rate="100"))
    rec = save(client, one_section(line), rate_basis=basis)
    html = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
    assert shown in html and hidden not in html
    assert _grid_ok(html)
    assert "1,000.00" in re.search(r"BASIC VALUE SUBTOTAL.*?</tr>", html, re.S).group(0)


def test_a_split_print_is_byte_identical_with_or_without_the_key(client):
    rec = save(client, one_section(a_line(supply_rate="100", install_rate="40")))
    with_key = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
    del rec["rate_basis"]
    without = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
    assert with_key == without
    assert "Installation<br/>U/ Rate" in without and "Supply Amount" in without


def test_changing_the_basis_changes_no_amount(client):
    rec = save(client, one_section(a_line(supply_rate="100")))
    figures = (rec["supply_subtotal"], rec["install_subtotal"], rec["subtotal"],
               [(l["supply_amount"], l["install_amount"]) for l in rec["line_items"]])
    for basis in ("sitc", "supply_only", "split"):
        rec["rate_basis"] = basis
        assert BQ.boq_totals(rec) == figures[:3]
        html = client.get(f"/boq/print/{rec['id']}").get_data(as_text=True)
        assert "1,000.00" in html


# ═══ 6. RA ═══════════════════════════════════════════════════════════════════

def test_an_sitc_line_bills_on_the_supply_leg_at_the_full_rate(client):
    rec = sitc_boq(client)
    conftest.chain_ready(rec["id"])
    lid = rec["line_items"][0]["line_id"]
    rates = ra.approved_rates(rec["id"])
    assert rates[(lid, "supply")] == 841920.0
    assert rates.get((lid, "installation")) is None
    assert lid in ra.no_rate_lines(rec["id"], "installation")
    assert lid not in ra.no_rate_lines(rec["id"], "supply")
    sup = client.get(f"/ra/create?boq={rec['id']}&leg=supply").get_data(as_text=True)
    assert f'id="q_{lid}"' in sup
    assert 'value="supply (SITC)"' in sup
    ins = client.get(f"/ra/create?boq={rec['id']}&leg=installation").get_data(as_text=True)
    assert f'id="q_{lid}"' not in ins, "the installation leg skips it: no rate"


def test_the_supply_leg_link_reads_supply_sitc(client):
    rec = sitc_boq(client)
    view = client.get(f"/boq/view/{rec['id']}").get_data(as_text=True)
    assert "RA &middot; Supply (SITC)" in view
    picker = client.get("/ra/create").get_data(as_text=True)
    assert ">Supply (SITC)</a>" in picker
    plain = save(client, one_section(a_line()))
    assert "RA &middot; Supply (SITC)" not in client.get(
        f"/boq/view/{plain['id']}").get_data(as_text=True)


# ═══ 7. Changing the basis — /boq/edit ═══════════════════════════════════════

def _edit_post(client, rec, **form):
    boot, _pf = BQ._form_payload_from(rec)
    data = {"date": rec["date"], "project_name": rec["project_name"],
            "account_name": rec["account_name"], "boq_json": json.dumps(boot)}
    data.update(form)
    return client.post(f"/boq/edit/{rec['id']}", data=data)


def test_the_edit_get_shows_the_basis_and_writes_nothing(client):
    rec = sitc_boq(client)
    before = copy.deepcopy(STORE["boqs"])
    html = client.get(f"/boq/edit/{rec['id']}").get_data(as_text=True)
    assert selected_basis(html) == "sitc"
    assert STORE["boqs"] == before


def test_the_edit_post_changes_the_basis_logs_it_and_moves_no_money(client):
    rec = save(client, one_section(a_line(supply_rate="100")))
    money = (rec["subtotal"], [l["supply_amount"] for l in rec["line_items"]])
    r = _edit_post(client, rec, rate_basis="sitc")
    assert r.status_code == 302
    assert rec["rate_basis"] == "sitc"
    assert (rec["subtotal"], [l["supply_amount"] for l in rec["line_items"]]) == money
    row = [e for e in rec["edit_log"] if e["field"].startswith("Rates are for")]
    assert row and row[0]["before"] == "split" and row[0]["after"] == "sitc"
    assert row[0]["by"] == conftest.ensure_test_user()["id"] and row[0]["at"]


def test_an_old_boq_edited_for_something_else_gains_no_key(client):
    rec = save(client, one_section(a_line(supply_rate="100")))
    del rec["rate_basis"]                                 # saved before today
    r = _edit_post(client, rec, rate_basis="split", notes="hello")
    assert r.status_code == 302
    assert "rate_basis" not in rec
    assert not [e for e in rec.get("edit_log") or [] if e["field"].startswith("Rates are for")]


def test_the_edit_refuses_a_basis_that_would_hide_a_rate(client):
    rec = save(client, one_section(a_line(item_no="4", supply_rate="100", install_rate="5")))
    before = copy.deepcopy(rec)
    r = _edit_post(client, rec, rate_basis="sitc")
    assert r.status_code == 200
    assert "item A 4" in r.get_data(as_text=True)
    assert rec == before


def test_the_edit_post_is_gated_by_boq_create(client):
    rec = sitc_boq(client)
    auth.ensure_builtin_roles()
    old = auth.find_user("basis-hr")
    if old:
        del STORE["users"][old["id"]]
    hr = auth.create_user("basis-hr", "HR Person", "basis-hr-password", ["role-hr"],
                          created_by="test")
    assert "boq.create" not in auth.permissions_of(hr)
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = hr["id"]
    before = copy.deepcopy(STORE["boqs"])
    assert client.get(f"/boq/edit/{rec['id']}").status_code == 403
    assert _edit_post(client, rec, rate_basis="split").status_code == 403
    assert STORE["boqs"] == before
