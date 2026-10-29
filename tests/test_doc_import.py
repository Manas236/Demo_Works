"""
Import from Excel on every other document (18 October 2026) — `docimport.py`,
the schema half of `sheetimport.py`, and the six create seams it lands on.

CLIENT_CHANGES.md §0, forty-eighth block. Every sheet here is built with
`sheetimport.from_rows()` — `read()` minus the workbook reader — and staged
through the REAL `docimport.stage()`, so this file needs no openpyxl and runs
in ABOUT.md §1's row-3 configuration too. The one test that uploads a real
.xlsx skips inside the function without openpyxl.

The rules each test below holds:

* every column is a dropdown, and **ignore** keeps a column out;
* the LEGEND lists the columns a document cannot be made without — and only
  those — on the upload page and, ticked off, on the preview;
* nothing is saved until the document's own Save (or a register's Create);
* a BOQ line is reached by `line_id`; a sheet's item number only PROPOSES one,
  and a number the schedule carries twice is never chosen for the operator;
* each kind carries its document's create permission, and draws its button
  where that document's create form is.
"""

import io
import re

import pytest

import auth
import boq as BQ
import conftest
import demo_data as DD
import docimport as DI
import sheetimport as SI
from store import STORE

SIFY = DD.BOQ_META["id"]


# ═══ Helpers ═════════════════════════════════════════════════════════════════

def staged(kind: str, rows, ctx=None, name="sheet.xlsx", sheet="Sheet1", more=()):
    wb = SI.from_rows([(sheet, "visible", rows), *more])
    return DI.stage(DI.KINDS[kind], wb, name, conftest.ensure_test_user()["id"], ctx or {})


def rec_of(tok):
    return STORE["doc_imports"][tok]


def form_of(tok, override=None, action="confirm", **extra):
    rec = rec_of(tok)
    form = {f"map_{c}": t for c, t in rec["mapping"].items()}
    for col, target in (override or {}).items():
        form[f"map_{col}"] = target
    form.update({"action": action, "sheet": str(rec["sheet_index"])})
    form.update(extra)
    return form


def confirm(client, kind, tok, override=None, **extra):
    return client.post(f"/import/{kind}/{tok}", data=form_of(tok, override, **extra))


def applied(client, kind, tok, override=None, **extra):
    r = confirm(client, kind, tok, override, **extra)
    assert r.status_code == 303, r.get_data(as_text=True)[:3000]
    assert r.headers["Location"].endswith(f"/import/{kind}/{tok}/apply")
    page = client.get(r.headers["Location"])
    return page


def sify(client):
    client.get("/boq/")                  # seeds the 56 specs and the demo BOQ
    return STORE["boqs"][SIFY]


def line(boq, section, item):
    hits = [li for li in boq["line_items"] if li["section"] == section
            and li["item_no"] == item and not li["is_header"]]
    assert len(hits) >= 1, (section, item)
    return hits


def a_user(role_id: str, name: str):
    auth.ensure_builtin_roles()
    return auth.find_user(name) or auth.create_user(
        name, name, f"{name}-password-123", [role_id], created_by="test")


# ═══ 1. The schema half of the reader ════════════════════════════════════════

SCH = {"targets": [
    SI.target("description", "Description", required=True, kw=r"descr",
              about="what it is"),
    SI.target("qty", "Quantity", required=True, kw=r"\bqty\b", avoid=r"rate",
              prefer=r"this", about="how many"),
    SI.target("rate", "Rate", kw=r"\brate\b", avoid=r"qty"),
], "any_of": [{"keys": ("rate",), "label": "a rate", "about": "x"}]}


def test_the_first_row_reading_as_two_targets_is_the_heading_and_a_typed_row_wins():
    wb = SI.from_rows([("S", "visible", [
        ["INDENT"], ["Description", "Qty", "Rate"], ["Pipe", 2, 10],
        ["Description", "Qty", "Rate"]])])
    g = wb["grid"][0]
    assert SI.schema_header(g, SCH) == [1, 1]
    assert SI.schema_header(g, SCH, row=3) == [2, 2]
    assert SI.schema_header(g, SCH, row=99) == []


def test_the_guess_is_leftmost_and_avoid_and_prefer_steer_it():
    wb = SI.from_rows([("S", "visible", [
        ["Description", "Qty rate", "BOQ Qty", "This bill Qty", "Rate"], ["x", 1, 2, 3, 4]])])
    g = wb["grid"][0]
    m = SI.schema_guess(g, SCH, SI.schema_header(g, SCH))
    assert m == {"0": "description", "1": "", "2": "", "3": "qty", "4": "rate"}


def test_confirm_refuses_a_duplicate_a_missing_required_and_an_unmet_any_of():
    wb = SI.from_rows([("S", "visible", [["Description", "Qty", "Rate"], ["x", 1, 2]])])
    g = wb["grid"][0]
    probs = SI.schema_problems(g, {"0": "description", "1": "description", "2": ""}, SCH)
    assert any("Description is chosen for 2 columns (A, B)" in p for p in probs)
    assert any("holds the Quantity" in p for p in probs)
    assert any("Choose a column for a rate" in p for p in probs)
    assert SI.schema_problems(g, {"0": "description", "1": "qty", "2": "rate"}, SCH) == []


def test_rows_skip_blank_rows_and_a_repeated_heading_and_keep_the_sheet_row_number():
    wb = SI.from_rows([("S", "visible", [
        ["Description", "Qty"], ["Pipe", 2], [None, None, "stray"], ["Description", "Qty"],
        ["Valve", "NA"]])])
    g = wb["grid"][0]
    rows, repeats = SI.schema_rows(g, {"0": "description", "1": "qty", "2": ""}, [0, 0])
    assert [r["row"] for r in rows] == [2, 5]
    assert repeats == 1
    assert rows[1]["cells"]["qty"][0] == "NA"


def test_cells_are_read_never_guessed():
    assert SI.cell_number("₹ 1,25,000.50") == (125000.5, "")
    assert SI.cell_number("12%", percent=True) == (12.0, "")
    assert SI.cell_number(0.12, "pct", percent=True) == (12.0, "")
    assert SI.cell_number("-") == (None, "")
    assert SI.cell_number("NA")[0] is None and "not a number" in SI.cell_number("NA")[1]
    assert SI.cell_number("9.3+1.5")[0] is None
    assert SI.cell_date("2026-04-01T00:00:00", "date") == ("2026-04-01", "")
    assert SI.cell_date("2026-04-01") == ("2026-04-01", "")
    v, why = SI.cell_date("01/04/2026")
    assert v == "" and "YYYY-MM-DD" in why, "a dd/mm or mm/dd date is never guessed"
    assert SI.cell_code(400001.0) == ("400001", "")
    assert SI.cell_item(4.0999999999999996) == ("4.1", "")


def test_the_reader_section_imports_nothing_from_the_app():
    """The leaf rule `tests/test_import_directions.py` holds for the whole
    file, restated for the section this pass added — it adds no import."""
    src = (conftest.REPO / "sheetimport.py").read_text(encoding="utf8")
    tail = src[src.index("# 9. ANY DOCUMENT"):]
    assert not re.search(r"^\s*(?:import|from)\s", tail, re.M)


# ═══ 2. The registry and the buttons ════════════════════════════════════════

def test_every_import_endpoint_carries_its_documents_create_permission():
    for key, kind in DI.KINDS.items():
        want = auth.ROUTE_PERMISSIONS[kind.endpoint]
        for page in ("upload", "preview", "apply"):
            assert auth.ROUTE_PERMISSIONS[f"docimport.{page}_{key}"] == want, (key, page)


def test_no_permission_was_minted_for_an_import():
    assert not any(p.startswith(("docimport", "import")) for p in auth.PERMISSIONS)


BUTTONS = [
    ("/purchase/create", "/import/purchase"),
    ("/address/add", "/import/address"),
    ("/spec/add", "/import/spec"),
    ("/employee/new", "/import/employee"),
    ("/quotation/create", "/import/quotation"),
]


@pytest.mark.parametrize("page,target", BUTTONS)
def test_the_create_form_draws_the_import_button(client, page, target):
    html = client.get(page).get_data(as_text=True)
    assert f'href="{target}"' in html, f"{page} has no Import from Excel button"


@pytest.mark.parametrize("route,kind", [("/dc/create", "challan"), ("/po/create", "dpo"),
                                        ("/measurement/create", "measurement")])
def test_the_schedule_forms_draw_the_button_carrying_their_schedule(client, route, kind):
    sify(client)
    html = client.get(f"{route}?boq={SIFY}").get_data(as_text=True)
    assert f'href="/import/{kind}?boq={SIFY}"' in html


def test_the_ra_form_draws_the_button_with_its_leg(client):
    sify(client)
    conftest.chain_ready(SIFY)
    html = client.get(f"/ra/create?boq={SIFY}&leg=installation").get_data(as_text=True)
    assert f'href="/import/ra?boq={SIFY}&leg=installation"' in html


def test_the_edit_forms_draw_no_import_button(client):
    client.get("/address/")
    aid = next(iter(STORE["addresses"]))
    assert "/import/address" not in client.get(f"/address/edit/{aid}").get_data(as_text=True)
    client.get("/spec/")
    sid = next(iter(STORE["specs"]))
    assert "/import/spec" not in client.get(f"/spec/edit/{sid}").get_data(as_text=True)


def test_the_product_mode_quotation_page_draws_no_import_button(client, catalogue_unhidden):
    """The pinned `1d7725a` page stays byte-identical — `test_quotation_switch`
    holds the bytes; this says why the button is absent there."""
    assert "/import/quotation" not in client.get("/quotation/create").get_data(as_text=True)


# ═══ 3. The upload page and the legend ══════════════════════════════════════

@pytest.mark.parametrize("kind", sorted(DI.KINDS))
def test_every_upload_page_renders_and_lists_only_the_required_columns(client, kind):
    sify(client)
    k = DI.KINDS[kind]
    q = f"?boq={SIFY}" if k.needs_boq else ""
    if kind == "ra":
        conftest.chain_ready(SIFY)
        q += "&leg=supply"
    html = client.get(f"/import/{kind}{q}").get_data(as_text=True)
    assert "Columns the sheet must have" in html
    sch = k.schema({"boq_id": SIFY} if k.needs_boq else {})
    for t in sch["targets"]:
        cell = f"<th>{DI.P.esc(t['label'])}</th>"
        if t["required"]:
            assert cell in html, f"{kind}: the legend misses {t['label']}"
        else:
            assert cell not in html, f"{kind}: the legend lists optional {t['label']}"
    for g in sch.get("any_of") or ():
        assert f"<th>{DI.P.esc(g['label'])}</th>" in html
    assert 'name="workbook"' in html


@pytest.mark.parametrize("kind", ["challan", "dpo", "measurement", "ra"])
def test_a_schedule_import_with_no_schedule_asks_which(client, kind):
    sify(client)
    html = client.get(f"/import/{kind}").get_data(as_text=True)
    assert "Which schedule is this" in html
    assert 'name="workbook"' not in html
    assert f"boq={SIFY}" in html
    if kind == "ra":
        assert "leg=supply" in html and "leg=installation" in html


def test_a_superseded_schedule_is_refused(client):
    sify(client)
    STORE["boqs"]["rev-1"] = dict(STORE["boqs"][SIFY], id="rev-1", supersedes=SIFY,
                                  rev_no=1, ref="SF/BOQ/26-27/0002")
    html = client.get(f"/import/challan?boq={SIFY}").get_data(as_text=True)
    assert "has been superseded" in html
    assert 'name="workbook"' not in html


def test_the_ra_import_is_refused_where_the_claim_would_be(client):
    """
    ⚠ **REWRITTEN 29 October 2026 — §0's fifty-eighth block, item 6.** The C1
    prerequisite is off (`ra.C1_PREREQUISITE`), so a supply claim with no
    challan is no longer refused and neither is the import that feeds it. The
    old assertion, verbatim:

        r = client.get(f"/import/ra?boq={SIFY}&leg=supply")
        assert r.status_code == 302, "no challan on the chain — C1 refuses supply"

    ⚠ **The INVARIANT is what matters and it still holds: the import is
    refused exactly where the CLAIM would be**, never on a rule of its own.
    That is what this now checks, from both sides — with the prerequisite off
    both open, and with it armed both refuse. A drift between them is the
    defect this test exists to catch, and it is now caught in either state.
    """
    sify(client)
    import ra

    # OFF — the shipped state. Neither is refused.
    assert ra.c1_prerequisite_on() is False
    assert client.get(f"/ra/create?boq={SIFY}&leg=supply").status_code == 200
    assert client.get(f"/import/ra?boq={SIFY}&leg=supply").status_code == 200

    # ARMED — both are, and for the same reason.
    saved = ra.C1_PREREQUISITE
    ra.C1_PREREQUISITE = True
    try:
        assert client.get(f"/ra/create?boq={SIFY}&leg=supply",
                          follow_redirects=False).status_code == 302
        assert client.get(f"/import/ra?boq={SIFY}&leg=supply").status_code == 302, (
            "the import must be refused exactly where the claim is")
    finally:
        ra.C1_PREREQUISITE = saved


def test_the_quotation_import_is_blocked_while_the_picker_reads_the_catalogue(
        client, catalogue_unhidden):
    html = client.get("/import/quotation").get_data(as_text=True)
    assert "reads the product catalogue" in html
    assert 'name="workbook"' not in html, "a form that can only be refused is not drawn"


def test_the_boq_import_draws_the_legend_too(client):
    html = client.get("/boq/import").get_data(as_text=True)
    assert "Columns the sheet must have" in html
    assert "<th>Description</th>" in html and "<th>Quantity (total)</th>" in html
    assert "Supply · unit rate" not in html.split("Columns the sheet must have")[1].split("</table>")[0]


# ═══ 4. The preview ══════════════════════════════════════════════════════════

PARTS = [["Sr", "Part", "HSN", "Unit", "Qty", "Rate", "Disc %"],
         ["1", "Gate valve 100mm", "84818090", "Nos", 4, 1850.5, 5],
         ["2", "Grinding wheel 4 inch", None, None, "NA", None, None],
         ["3", None, None, None, 2, 99, None]]


def test_the_preview_ticks_the_legend_off_as_columns_are_chosen(client):
    tok = staged("purchase", PARTS)
    html = client.get(f"/import/purchase/{tok}").get_data(as_text=True)
    assert "&#10003; column B" in html and "&#10003; column E" in html
    rec_of(tok)["mapping"]["4"] = ""
    html = client.get(f"/import/purchase/{tok}").get_data(as_text=True)
    assert "&#10007; not chosen yet" in html
    assert "Choose the column that holds the Quantity." in html


def test_confirm_is_refused_until_the_required_columns_are_chosen(client):
    tok = staged("purchase", PARTS)
    r = confirm(client, "purchase", tok, {"1": ""})
    assert r.status_code == 200
    assert "Before this can open as a purchase order" in r.get_data(as_text=True)
    assert not rec_of(tok)["confirmed"]


def test_ignore_keeps_a_column_out(client):
    tok = staged("purchase", PARTS)
    html = applied(client, "purchase", tok, {"2": ""}).get_data(as_text=True)
    assert "84818090" not in html, "an ignored column went through"
    assert 'value="Gate valve 100mm"' in html


def test_the_heading_row_can_be_typed(client):
    """A title row that reads as a heading is taken first; typing the real
    heading's row moves it, and the guess is redone for that row."""
    tok = staged("purchase", [["Part description register", "Qty sheet"]] + PARTS)
    assert rec_of(tok)["header_row"] is None
    assert DI._effective(DI.KINDS["purchase"], rec_of(tok))[2] == [0, 0]
    r = client.post(f"/import/purchase/{tok}", data={
        "action": "update", "sheet": "0", "header_row": "2"})
    assert r.status_code == 303
    assert rec_of(tok)["header_row"] == 2
    assert rec_of(tok)["mapping"]["1"] == "description"
    assert rec_of(tok)["mapping"]["4"] == "qty"


def test_another_sheet_starts_afresh(client):
    tok = staged("purchase", PARTS, more=[("Two", "visible", [["Name", "Quantity"], ["a", 1]])])
    rec = rec_of(tok)
    rec["header_row"] = 1
    other = 1 - rec["sheet_index"]
    r = client.post(f"/import/purchase/{tok}", data={"action": "update", "sheet": str(other)})
    assert r.status_code == 303
    assert rec_of(tok)["sheet_index"] == other and rec_of(tok)["header_row"] is None


def test_a_hidden_sheet_is_never_chosen_for_you(client):
    tok = staged("purchase", [["x"]], more=[("Hidden", "hidden", PARTS)])
    assert rec_of(tok)["sheet_index"] == 0


def test_a_confirmed_layout_is_offered_next_time_and_never_skips_the_preview(client):
    tok = staged("purchase", PARTS)
    confirm(client, "purchase", tok, {"2": ""})
    tok2 = staged("purchase", PARTS)
    assert rec_of(tok2)["known"] is True
    assert rec_of(tok2)["mapping"]["2"] == "", "the confirmed ignore was remembered"
    assert client.get(f"/import/purchase/{tok2}").status_code == 200


def test_a_token_is_the_uploaders_and_this_kinds_only(client):
    tok = staged("purchase", PARTS)
    assert client.get(f"/import/address/{tok}").status_code == 404, \
        "a purchase-order token is not a way into the address book"
    rec_of(tok)["user_id"] = "somebody-else"
    assert client.get(f"/import/purchase/{tok}").status_code == 404


def test_an_old_import_is_purged(client):
    tok = staged("purchase", PARTS)
    rec_of(tok)["created_ts"] -= DI.STAGE_TTL_SECONDS + 5
    assert client.get(f"/import/purchase/{tok}").status_code == 404
    assert tok not in STORE["doc_imports"]


def test_a_user_keeps_at_most_ten(client):
    toks = [staged("purchase", PARTS) for _ in range(DI.MAX_STAGED_PER_USER + 2)]
    assert sum(t in STORE["doc_imports"] for t in toks) == DI.MAX_STAGED_PER_USER


def test_a_sheet_too_long_for_the_document_is_refused_whole(client):
    rows = [["Part", "Qty"]] + [[f"p{i}", 1] for i in range(DI.KINDS["purchase"].max_rows + 1)]
    tok = staged("purchase", rows)
    r = confirm(client, "purchase", tok)
    assert "Split it — nothing is cut off" in r.get_data(as_text=True)


def test_the_preview_escapes_what_came_out_of_the_workbook(client):
    pay = "<script>alert(1)</script>"
    tok = staged("purchase", [["Part", "Qty"], [pay, 1]], name=f"x{pay}.xlsx", sheet=f"S{pay}")
    html = client.get(f"/import/purchase/{tok}").get_data(as_text=True)
    assert pay not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    html = applied(client, "purchase", tok).get_data(as_text=True)
    assert pay not in html


# ═══ 5. Purchase order ═══════════════════════════════════════════════════════

def test_the_parts_arrive_on_the_order_form_and_nothing_is_saved(client):
    before = dict(STORE["purchases"])
    tok = staged("purchase", PARTS)
    html = applied(client, "purchase", tok).get_data(as_text=True)
    assert 'action="/purchase/create"' in html
    assert 'value="Gate valve 100mm"' in html and 'value="1850.5"' in html
    assert 'value="84818090"' in html and 'value="5"' in html
    assert "Nothing has been saved" in html
    assert STORE["purchases"] == before


def test_a_part_with_figures_and_no_description_is_left_out_and_said(client):
    tok = staged("purchase", PARTS)
    html = applied(client, "purchase", tok).get_data(as_text=True)
    assert "Row 4: Figures but no description" in html
    assert 'value="99"' not in html


def test_a_word_in_the_quantity_is_left_blank_and_said(client):
    tok = staged("purchase", PARTS)
    built = DI._built(DI.KINDS["purchase"], rec_of(tok))
    wheel = next(i for i in built["items"] if i["description"].startswith("Grinding"))
    assert wheel["qty"] == ""
    assert any(n["row"] == 3 and "Quantity" in n["msg"] for n in built["notes"])


def test_the_prefilled_parts_save_through_the_ordinary_order_post(client):
    client.get("/address/")
    vendor = next(a for a in STORE["addresses"].values() if a["type"] == "vendor")
    tok = staged("purchase", PARTS[:2])
    built = DI._built(DI.KINDS["purchase"], rec_of(tok))
    it = built["items"][0]
    r = client.post("/purchase/create", data={
        "date": "2026-10-18", "vendor_id": vendor["id"], "status": "Draft",
        "tax_type": "exempt", "extra_desc": it["description"], "extra_unit": it["unit"],
        "extra_qty": it["qty"], "extra_rate": it["rate"], "extra_discount": it["discount"],
        "extra_hsn": it["hsn"]})
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    po = next(iter(STORE["purchases"].values()))
    xl = po["extra_lines"][0]
    assert (xl["description"], xl["qty"], xl["rate"], xl["discount_pct"], xl["hsn"]) == \
        ("Gate valve 100mm", 4.0, 1850.5, 5.0, "84818090")
    assert "line_id" not in xl


# ═══ 6. Quotation ════════════════════════════════════════════════════════════

def _spec_with(n_variants):
    client_specs = STORE["specs"]
    return next(s for s in client_specs.values() if len(s["variants"]) == n_variants
                and s["variants"][0].get("default_supply_base_rate"))


def test_a_spec_code_becomes_a_supply_pick_with_the_library_rate(client):
    client.get("/spec/")
    s = _spec_with(1)
    tok = staged("quotation", [["Code", "Qty"], [s["code"], 3]])
    built = DI._built(DI.KINDS["quotation"], rec_of(tok))
    pick = built["items"][0]
    assert (pick["sid"], pick["vidx"], pick["leg"], pick["qty"]) == (s["id"], 0, "supply", 3.0)
    assert pick["price"] == s["variants"][0]["default_supply_base_rate"]


def test_the_sheets_own_rate_is_the_price(client):
    client.get("/spec/")
    s = _spec_with(1)
    tok = staged("quotation", [["Code", "Qty", "Rate"], [s["code"], 3, 777]])
    assert DI._built(DI.KINDS["quotation"], rec_of(tok))["items"][0]["price"] == 777.0


def test_a_title_word_for_word_is_a_match_and_anything_else_is_not(client):
    client.get("/spec/")
    s = _spec_with(1)
    tok = staged("quotation", [["Description", "Qty"], [s["title"].upper(), 1],
                               [s["title"] + " (approx)", 1]])
    built = DI._built(DI.KINDS["quotation"], rec_of(tok))
    assert [p["sid"] for p in built["items"]] == [s["id"]]
    assert any(n["row"] == 3 and n["level"] == "red" for n in built["notes"])


def test_a_sized_clause_with_no_size_waits_for_your_choice(client):
    client.get("/spec/")
    s = next(x for x in STORE["specs"].values() if len(x["variants"]) > 2)
    tok = staged("quotation", [["Code", "Qty"], [s["code"], 2]])
    page = client.get(f"/import/quotation/{tok}").get_data(as_text=True)
    assert "Rows that need you to choose the clause" in page
    assert not DI._built(DI.KINDS["quotation"], rec_of(tok))["items"]
    html = applied(client, "quotation", tok, **{"match_2": f"{s['id']}:1"}).get_data(as_text=True)
    assert 'action="/quotation/create"' in html
    sel = re.search(r'id="prev-sel-data">(.*?)</script>', html, re.S).group(1)
    assert f'"sid": "{s["id"]}"' in sel and '"vidx": 1' in sel


def test_a_size_named_exactly_is_matched(client):
    client.get("/spec/")
    s = next(x for x in STORE["specs"].values() if len(x["variants"]) > 2)
    label = s["variants"][2]["label"]
    tok = staged("quotation", [["Code", "Size", "Qty"], [s["code"], label, 2]])
    assert DI._built(DI.KINDS["quotation"], rec_of(tok))["items"][0]["vidx"] == 2


def test_an_unknown_code_is_listed_not_imported(client):
    client.get("/spec/")
    tok = staged("quotation", [["Code", "Qty"], ["NO-SUCH-CODE", 2]])
    built = DI._built(DI.KINDS["quotation"], rec_of(tok))
    assert not built["items"]
    assert "NO-SUCH-CODE" in built["notes"][0]["msg"]


def test_a_refused_quotation_post_cannot_break_out_of_its_script_block(client):
    """The reflected sink this pass closed: the posted `selections_json` was
    dropped raw into `<script type="application/json">`."""
    pay = '[{"x": "</script><script>alert(9)</script>"}]'
    html = client.post("/quotation/create", data={"account_name": "",
                                                  "selections_json": pay}).get_data(as_text=True)
    assert "</script><script>alert(9)" not in html
    assert "\\u003c/script\\u003e" in html


# ═══ 7. Measurement grid ═════════════════════════════════════════════════════

GRID = [["Location", "25 NB", "40", "MSA", "Remarks"],
        ["H1", 12.5, None, 4, "riser"],
        ["B2", "NA", 7, -1, None],
        [None, 3, None, None, None]]


def test_the_grid_columns_come_from_settings_and_are_guessed_by_their_size(client):
    sify(client)
    tok = staged("measurement", GRID, {"boq_id": SIFY})
    m = rec_of(tok)["mapping"]
    assert m == {"0": "label", "1": "g_d25", "2": "g_d40", "3": "g_msa", "4": "remarks"}


def test_the_grid_arrives_on_the_measurement_form(client):
    sify(client)
    tok = staged("measurement", GRID, {"boq_id": SIFY})
    html = applied(client, "measurement", tok).get_data(as_text=True)
    assert f'action="/measurement/create?boq={SIFY}"' in html
    assert 'value="H1"' in html and 'data-key="d25" value="12.5"' in html
    assert 'value="riser"' in html
    assert "d25: “NA” is not a number" in html and "negative measurement" in html
    assert "Figures but no location" in html


def test_a_refused_measurement_save_keeps_the_grid_that_was_typed(client):
    sify(client)
    grid = '{"rows":[{"label":"Typed loc","values":{"d25":"9"},"remarks":"kept"}]}'
    html = client.post(f"/measurement/create?boq={SIFY}", data={
        "date": "", "grid_json": grid, "ms_json": '{"lines":[]}'}).get_data(as_text=True)
    assert "A measurement date is required." in html
    assert 'value="Typed loc"' in html and 'value="kept"' in html, \
        "the grid was reseeded and the typed rows were lost"


# ═══ 8. Challan / draft PO / RA — matched on line_id ════════════════════════

def _dc(client, rows):
    sify(client)
    return staged("challan", rows, {"boq_id": SIFY})


def test_a_unique_item_number_is_matched_and_ticked_at_the_sheets_quantity(client):
    b = sify(client)
    lid = line(b, "A", "4.1")[0]["line_id"]
    tok = _dc(client, [["Item", "Qty"], ["4.1", 3]])
    html = applied(client, "challan", tok).get_data(as_text=True)
    assert f'id="c_{lid}" checked' in html
    assert f'id="q_{lid}"\n              value="3"' in html
    other = line(b, "A", "4.2")[0]["line_id"]
    assert f'id="c_{other}" checked' not in html, "an unmatched line arrived ticked"
    assert f'action="/dc/create?boq={SIFY}"' in html


def test_a_number_the_schedule_carries_twice_is_never_chosen_for_you(client):
    b = sify(client)
    a17 = [li["line_id"] for li in line(b, "A", "17")]
    tok = _dc(client, [["Section", "Item", "Qty"], ["A", "17", 1]])
    built = DI._built(DI.KINDS["challan"], rec_of(tok))
    assert not built["items"]
    assert "on the schedule 2 times" in built["notes"][0]["msg"]
    page = client.get(f"/import/challan/{tok}").get_data(as_text=True)
    assert "choose which line" in page
    for lid in a17:
        assert f'value="{lid}"' in page
    html = applied(client, "challan", tok, **{"match_2": a17[1]}).get_data(as_text=True)
    assert f'id="c_{a17[1]}" checked' in html and f'id="c_{a17[0]}" checked' not in html


def test_the_section_column_picks_the_line_in_that_section(client):
    b = sify(client)
    b17 = line(b, "B", "17")[0]["line_id"]
    tok = _dc(client, [["Section", "Item", "Qty"], ["Section B", "17", 2]])
    assert DI._built(DI.KINDS["challan"], rec_of(tok))["items"][0]["lid"] == b17


def test_a_description_word_for_word_settles_a_repeated_number(client):
    b = sify(client)
    a17 = line(b, "A", "17")
    if a17[0]["description"] == a17[1]["description"]:
        pytest.skip("the two A·17 lines carry the same text on this seed")
    tok = _dc(client, [["Section", "Item", "Description", "Qty"],
                       ["A", "17", a17[1]["description"], 1]])
    assert DI._built(DI.KINDS["challan"], rec_of(tok))["items"][0]["lid"] == a17[1]["line_id"]


def test_a_specification_header_is_named_as_one(client):
    sify(client)
    tok = _dc(client, [["Section", "Item", "Qty"], ["A", "4", 1]])
    note = DI._built(DI.KINDS["challan"], rec_of(tok))["notes"][0]["msg"]
    assert "specification header" in note


def test_two_rows_for_one_line_are_not_added_up_for_you(client):
    sify(client)
    tok = _dc(client, [["Item", "Qty"], ["4.1", 1], ["4.1", 2]])
    built = DI._built(DI.KINDS["challan"], rec_of(tok))
    assert [i["qty"] for i in built["items"]] == ["1"]
    assert "row 2 already gives a quantity" in built["notes"][0]["msg"]


def test_a_blank_or_zero_quantity_is_not_prefilled(client):
    sify(client)
    tok = _dc(client, [["Item", "Qty"], ["4.1", None], ["4.2", 0], ["4.3", "NA"], ["4.4", 1]])
    built = DI._built(DI.KINDS["challan"], rec_of(tok))
    assert [i["qty"] for i in built["items"]] == ["1"]


def test_posting_the_proposals_back_unchanged_is_not_a_choice(client):
    """Every row's dropdown is posted with the preview. A value equal to the
    automatic proposal must not be stored as the operator's choice — it would
    freeze a proposal that the next mapping change has to redo."""
    b = sify(client)
    lid = line(b, "A", "4.1")[0]["line_id"]
    tok = _dc(client, [["Item", "Qty"], ["4.1", 1], ["17", 1]])
    client.post(f"/import/challan/{tok}", data=form_of(
        tok, action="update", match_2=lid, match_3=""))
    assert rec_of(tok)["matches"] == {}


def test_a_changed_mapping_drops_the_choices_made_for_the_old_one(client):
    b = sify(client)
    a17 = [li["line_id"] for li in line(b, "A", "17")]
    b17 = line(b, "B", "17")[0]["line_id"]
    tok = _dc(client, [["Section", "Item", "Qty"], ["B", "17", 1]])
    rec_of(tok)["mapping"]["0"] = ""            # no Section column yet
    client.post(f"/import/challan/{tok}", data=form_of(tok, action="update",
                                                         match_2=a17[0]))
    assert rec_of(tok)["matches"] == {"2": a17[0]}, "a real change is a choice"
    # The operator now maps the Section column: the proposal is redone (B·17)
    # and the choice made against the old mapping does not override it.
    client.post(f"/import/challan/{tok}", data=form_of(
        tok, {"0": "section"}, action="update", match_2=a17[0]))
    assert rec_of(tok)["matches"] == {}
    assert DI._built(DI.KINDS["challan"], rec_of(tok))["items"][0]["lid"] == b17


def test_a_posted_line_that_is_not_on_the_schedule_is_ignored(client):
    sify(client)
    tok = _dc(client, [["Item", "Qty"], ["4.1", 1]])
    rec_of(tok)["matches"] = {"2": "not-a-line"}
    assert DI._built(DI.KINDS["challan"], rec_of(tok))["items"][0]["lid"] == \
        line(STORE["boqs"][SIFY], "A", "4.1")[0]["line_id"]


def test_the_draft_po_carries_the_pieces(client):
    b = sify(client)
    lid = line(b, "A", "4.1")[0]["line_id"]
    tok = staged("dpo", [["Item", "Order qty", "Pcs"], ["4.1", 6, 1]], {"boq_id": SIFY})
    html = applied(client, "dpo", tok).get_data(as_text=True)
    assert f'id="p_{lid}"\n              value="1"' in html
    assert f'action="/po/create?boq={SIFY}"' in html


def test_the_ra_takes_this_bills_quantity_not_the_boqs(client):
    b = sify(client)
    conftest.chain_ready(SIFY)
    lid = line(b, "A", "4.2")[0]["line_id"]
    tok = staged("ra", [["Item", "BOQ Qty", "This bill qty", "Rate"], ["4.2", 12, 5, 600]],
                 {"boq_id": SIFY, "leg": "supply"})
    assert rec_of(tok)["mapping"]["2"] == "qty"
    html = applied(client, "ra", tok).get_data(as_text=True)
    assert f'id="q_{lid}"\n              value="5"' in html
    assert f'id="r_{lid}"\n              value="600"' in html
    assert 'action="/ra/create?boq=' in html


def test_an_imported_claim_is_still_held_by_the_over_claim_block(client):
    b = sify(client)
    conftest.chain_ready(SIFY)
    li = line(b, "A", "4.2")[0]
    r = client.post(f"/ra/create?boq={SIFY}&leg=supply", data={
        "date": "2026-10-18",
        "ra_json": '{"lines":[{"line_id":"%s","qty":"%s","rate":"1"}]}' % (
            li["line_id"], li["total_qty"] + 1)})
    assert r.status_code == 200 and not STORE["ra_bills"], "the over-claim block let it through"


def test_an_imported_ra_writes_no_source_key(client):
    """The manual path: a bill raised from an imported prefill names no challan
    and no sheet — `source_dc_ids` / `source_ms_ids` stay absent."""
    b = sify(client)
    conftest.chain_ready(SIFY)
    li = line(b, "A", "4.2")[0]
    r = client.post(f"/ra/create?boq={SIFY}&leg=supply", data={
        "date": "2026-10-18",
        "ra_json": '{"lines":[{"line_id":"%s","qty":"1","rate":"1"}]}' % li["line_id"]})
    assert r.status_code == 302
    bill = next(iter(STORE["ra_bills"].values()))
    assert "source_dc_ids" not in bill and "source_ms_ids" not in bill


# ═══ 9. The three registers ══════════════════════════════════════════════════

ADDR = [["Name", "Type", "Address", "City", "State", "PIN", "Phone", "GSTIN"],
        ["Acme Pipes", "Vendor", "Plot 4, MIDC", "Pune", "maharashtra", 411019, 9820041122, None],
        ["No State Co", None, "Unit 2", "Pune", "MH", 411019, None, None],
        ["Bad GST Co", None, "Unit 3", "Pune", "Maharashtra", 411019, None, "27AAAAA0000A1Z9"]]


def test_the_review_page_lists_every_row_and_saves_nothing(client):
    before = len(STORE["addresses"])
    tok = staged("address", ADDR)
    r = applied(client, "address", tok)
    html = r.get_data(as_text=True)
    assert "<b>1</b> row will be added" in html and "<b>2</b> will not" in html
    assert "Acme Pipes" in html and "&#10003; will be added" in html
    assert "Please pick a State" in html
    assert len(STORE["addresses"]) == before


def test_create_writes_only_the_rows_that_pass_through_the_address_books_own_write(client):
    client.get("/address/")
    before = set(STORE["addresses"])
    tok = staged("address", ADDR)
    applied(client, "address", tok)
    r = client.post(f"/import/address/{tok}/apply")
    assert r.status_code == 302
    new = [STORE["addresses"][k] for k in set(STORE["addresses"]) - before]
    assert [a["label"] for a in new] == ["Acme Pipes"]
    a = new[0]
    assert (a["type"], a["state"], a["pincode"], a["phone"], a["company"]) == \
        ("vendor", "Maharashtra", "411019", "9820041122", "Acme Pipes")
    assert tok not in STORE["doc_imports"], "the import is consumed"
    assert client.post(f"/import/address/{tok}/apply").status_code == 404, \
        "a second press must not create everything twice"


def test_a_label_already_in_the_book_is_not_added_twice(client):
    client.get("/address/")
    existing = next(iter(STORE["addresses"].values()))
    tok = staged("address", [ADDR[0], [existing["label"], None, "x", "Pune", "Maharashtra",
                                        411019, None, None]])
    built = DI._built(DI.KINDS["address"], rec_of(tok))
    assert "already in the book" in built["items"][0]["error"]


def test_rows_with_no_type_take_the_preview_choice(client):
    tok = staged("address", [["Label", "Address", "City", "State", "PIN"],
                             ["Site X", "Plot 1", "Pune", "Maharashtra", 411001]])
    client.post(f"/import/address/{tok}", data=form_of(tok, action="update", opt_type="site"))
    built = DI._built(DI.KINDS["address"], rec_of(tok))
    assert built["items"][0]["data"]["type"] == "site"


SPECS = [["Code", "Title", "Specification", "Category", "Size", "Unit", "Supply rate"],
         ["IMP-PIPE", "Imported pipe", "MS pipe, IS 1239", "piping", "25 mm", "Mtrs", 400],
         [None, None, None, None, "50 mm", "Mtrs", 600],
         ["IMP-PIPE", None, None, None, "80 mm", "Mtrs", 900],
         ["IMP-FLOW", "Flow switch", "Flow switch, UL", "Valves", None, "Nos", 2500]]


def test_rows_sharing_a_code_become_one_clause_in_several_sizes(client):
    client.get("/spec/")
    tok = staged("spec", SPECS)
    built = DI._built(DI.KINDS["spec"], rec_of(tok))
    pipe, flow = built["items"]
    assert not pipe["error"] and not flow["error"]
    assert [v["label"] for v in pipe["data"]["variants"]] == ["25 mm", "50 mm", "80 mm"]
    assert pipe["data"]["category"] == "Piping"
    assert [v["default_supply_base_rate"] for v in pipe["data"]["variants"]] == [400, 600, 900]
    assert len(flow["data"]["variants"]) == 1


def test_a_code_already_in_the_library_is_refused(client):
    client.get("/spec/")
    code = next(iter(STORE["specs"].values()))["code"]
    tok = staged("spec", [SPECS[0], [code, "T", "text", None, None, None, None]])
    err = DI._built(DI.KINDS["spec"], rec_of(tok))["items"][0]["error"]
    assert "already used by another spec" in err and "&quot;" not in err


def test_the_specs_are_created_through_the_librarys_own_write(client):
    client.get("/spec/")
    tok = staged("spec", SPECS)
    applied(client, "spec", tok)
    client.post(f"/import/spec/{tok}/apply")
    from spec import spec_by_code
    assert spec_by_code("IMP-PIPE") and spec_by_code("IMP-FLOW")


EMPS = [["Name", "Emp Code", "Designation", "Site", "Date of joining", "Day rate", "Active"],
        ["Ramesh Patil", "SF-014", "Fitter", None, "2026-04-01", 1200, "Yes"],
        ["Suresh Kale", "SF-014", "Helper", None, None, 800, None],
        ["Anil More", "SF-016", "Welder", "Nowhere Site", None, 900, None],
        ["Vijay", "SF-017", None, None, "01/04/2026", None, None]]


def test_employees_are_checked_one_rule_at_a_time(client):
    tok = staged("employee", EMPS)
    items = DI._built(DI.KINDS["employee"], rec_of(tok))["items"]
    assert not items[0]["error"]
    assert items[0]["data"]["day_rate"] == 1200.0 and items[0]["data"]["active"] is True
    assert "already has the code SF-014" in items[1]["error"]
    assert "no site called “Nowhere Site”" in items[2]["error"]
    assert "YYYY-MM-DD" in items[3]["error"]


def test_a_site_is_matched_to_the_address_book_exactly(client):
    client.get("/address/")
    site = next((a for a in STORE["addresses"].values() if a["type"] in ("site", "office")))
    tok = staged("employee", [EMPS[0][:4], ["Ramesh", "SF-1", "Fitter", site["label"]],
                              ["Mahesh", "SF-2", "Fitter", site["label"].upper()]])
    items = DI._built(DI.KINDS["employee"], rec_of(tok))["items"]
    assert items[0]["data"]["site_address_id"] == site["id"]
    if site["label"].upper() != site["label"]:
        assert items[1]["error"], "a site spelled differently must not be matched"


def test_the_employees_are_created_through_the_registers_own_write(client):
    tok = staged("employee", EMPS[:2])
    applied(client, "employee", tok)
    assert client.post(f"/import/employee/{tok}/apply").status_code == 302
    (e,) = STORE["employees"].values()
    assert (e["name"], e["code"], e["day_rate"], e["date_joined"]) == \
        ("Ramesh Patil", "SF-014", 1200.0, "2026-04-01")
    assert "rate_model" not in e


# ═══ 10. Access ══════════════════════════════════════════════════════════════

def test_a_role_without_the_documents_create_permission_is_refused_the_import(client):
    """Accountant holds `purchase.view` but not `purchase.create` — refused at
    every one of the three, and the gate is the registry's, not ours."""
    import app as app_module
    u = a_user("role-accountant", "acct-importer")
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s[auth.SESSION_KEY] = u["id"]
    tok = staged("purchase", PARTS)
    STORE["doc_imports"][tok]["user_id"] = u["id"]
    for url in ("/import/purchase", f"/import/purchase/{tok}", f"/import/purchase/{tok}/apply"):
        assert c.get(url).status_code in (302, 403), url


# ═══ 11. A real workbook, end to end ═════════════════════════════════════════

def test_a_real_xlsx_upload_reaches_the_preview(client):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in PARTS:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/import/purchase", data={"workbook": (io.BytesIO(buf.getvalue()), "parts.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 303, r.get_data(as_text=True)[:500]
    tok = r.headers["Location"].split("/import/purchase/")[1]
    assert rec_of(tok)["mapping"]["1"] == "description"
    assert "Gate valve 100mm" in client.get(r.headers["Location"]).get_data(as_text=True)
