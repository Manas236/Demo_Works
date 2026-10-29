"""
HSN/SAC — ONE rule, six surfaces (29 October 2026, CLIENT_CHANGES.md §0
**fifty-ninth** block, A1).

    any code while the document is a DRAFT; from issued onward, only a BLANK
    one may be FILLED

The predicate is `hsnfill.editable()`, and the point of this file is that there
is only ever **one** of it: `purchase.hsn_editable()` delegates to it, and the
BOQ, the spec library, the proforma, the tax invoice and the RA bill read the
same function. `tests/test_po_hsn_edit.py` holds the purchase order's own
behaviour unchanged with the assertions it was written with; nothing here
restates it.

⚠ No assertion in this file passes against a blank page: each names a code that
  only appears when the feature worked, a refusal sentence, or a digest.
"""

import pathlib

import pytest

import auth
import boq as BQ
import hsnfill as HF
import invoice as INV
import pipeline as P
import purchase as PUR
from store import STORE
from conftest import printable


# ═══ 0. The predicate itself ════════════════════════════════════════════════

def test_the_predicate_is_the_whole_rule_and_nothing_else():
    """Four cases, and they are the four the ruling names."""
    assert HF.editable(True, "") is True          # draft, blank  -> yes
    assert HF.editable(True, "73072900") is True  # draft, filled -> yes
    assert HF.editable(False, "") is True         # issued, blank -> the FILL
    assert HF.editable(False, "73072900") is False  # issued, printed -> never


def test_whitespace_only_is_blank_and_not_a_printed_code():
    assert HF.editable(False, "   ") is True
    assert HF.editable(False, "\t\n") is True


def test_the_purchase_order_predicate_delegates_rather_than_repeating():
    """
    ⚠ The one thing this pass must NOT have done is write a second predicate.
    `1fdc09e` built the rule for the purchase order; A1 generalised it.
    """
    import inspect
    src = inspect.getsource(PUR.hsn_editable)
    assert "HF.editable(" in src, "purchase.py must read the leaf's predicate"
    assert '== "Draft"' not in src.split('"""')[-1], (
        "the status literal belongs to is_draft(); hsn_editable() must not "
        "carry a second copy of the rule")
    assert PUR.HSN_MAX is HF.HSN_MAX


def test_the_cap_is_one_number_everywhere():
    assert HF.HSN_MAX == 8
    assert HF.clean("123456789999") == "12345678"
    assert HF.clean("  73072900  ") == "73072900"
    assert HF.clean(None) == ""


# ═══ 1. A blank code prints a DASH, never the amber chip ════════════════════

def test_a_blank_code_prints_an_em_dash():
    assert HF.print_cell("") == "&mdash;"
    assert HF.print_cell(None) == "&mdash;"
    assert HF.print_cell("   ") == "&mdash;"


def test_a_code_prints_escaped_and_the_entity_is_not_double_escaped():
    """
    `esc(x) or '&mdash;'`, never `esc(x or '&mdash;')` — the mistake
    `tests/test_entity_fallbacks.py` exists to catch.
    """
    assert HF.print_cell("<b>73") == "&lt;b&gt;73"
    assert "&amp;mdash;" not in HF.print_cell("")


def test_the_leaf_never_reaches_the_amber_chip():
    """
    ⚠ The whole point of `print_cell()` is that it does NOT call
    `branding.field()`. An import of the module that owns the chip is how it
    comes back, so the absence is asserted, not assumed.
    """
    import ast
    import pathlib
    src = pathlib.Path(HF.__file__).read_text(encoding="utf8")
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert "branding" not in names
    assert "todo-chip" not in src


def test_the_amber_chip_still_exists_for_the_fields_it_is_for():
    """The chip was not deleted — only the HSN cell stopped calling it."""
    import branding as B
    assert 'class="todo-chip">add GSTIN' in B.field("", "GSTIN")


# ═══ 2. The screen note — never printed ═════════════════════════════════════

def _entry(code="", desc="Butterfly valve", label="1"):
    line = {"hsn": code}
    return HF.entry("li:0", 1, label, desc, line)


def test_the_note_names_the_lines_with_no_code():
    note = HF.screen_note([_entry(""), _entry("7307", desc="Elbow", label="2")],
                          "/invoice/hsn/x", "tax invoice")
    assert "HSN/SAC is missing on 1 line." in note
    assert "Butterfly valve" not in note, "the LABEL names it, not the description"
    assert "<li>1</li>" in note
    assert 'href="/invoice/hsn/x"' in note
    assert "never printed on the tax invoice" in note


def test_the_note_is_empty_when_every_line_has_a_code():
    """Which is what keeps it off a complete document and off its golden."""
    assert HF.screen_note([_entry("7307"), _entry("8481")], "/x") == ""


def test_the_note_is_escaped():
    note = HF.screen_note([_entry("", label="<script>x</script>")], "/x")
    assert "<script>x</script>" not in note
    assert "&lt;script&gt;" in note


@pytest.mark.parametrize("url", [
    "/invoice/view/{iid}", "/proforma/view/{pid}", "/purchase/view/{oid}",
])
def test_the_note_sits_above_the_sheet_so_print_css_withholds_it(client, url):
    """
    ⚠ **The mechanism, asserted rather than trusted.** `PRINT_EDGE_CSS`'s
    `main > :has(~ .doc-outer) { display:none !important }` is what keeps a
    screen panel off paper, and it only works for markup that is a SIBLING
    BEFORE `.doc-outer`. A note that drifted below it would print on the
    customer's copy.
    """
    ids = _seed_chain(client)
    page = client.get(url.format(**ids)).get_data(as_text=True)
    if "hf-note" not in page:
        pytest.skip("this document has no missing code to report")
    assert page.index("hf-note") < page.index('<div class="doc-outer">')


@pytest.mark.parametrize("url", ["/invoice/view/{iid}", "/proforma/view/{pid}"])
def test_no_print_route_carries_the_note(client, url):
    """A print route renders the sheet alone; the note is a screen panel."""
    ids = _seed_chain(client)
    page = client.get(url.format(**ids)).get_data(as_text=True)
    sheet = page.split('<div class="doc-outer">', 1)[1]
    assert "hf-note" not in sheet


# ═══ 3. The seed — one chain, every document on it ══════════════════════════

def _seed_chain(client):
    """
    A BOQ, a proforma and a tax invoice, each with ONE line carrying no code
    and one carrying a printed one — and a Draft purchase order.

    Written as dicts rather than posted through the forms for
    `test_print_golden.py`'s reason: a record whose own id is random cannot be
    addressed by a parametrised test.
    """
    STORE["boqs"]["hf-boq"] = {
        "id": "hf-boq", "ref": "SF/BOQ/26-27/0901", "fy": "26-27",
        "date": "2026-10-29", "rev_no": 0, "supersedes": "",
        "project_id": "", "project_name": "HSN Test", "site_location": "Navi Mumbai",
        "account_name": "Acme Contractors", "contact_person": "", "to": "",
        "bill_gstin": "", "ship_same": True, "sections": [{"code": "A", "title": "A", "areas": []}],
        "blank_model": "as_is",
        "line_items": [
            {"line_id": "aaaaaaaaaaaa", "item_no": "1", "parent_item_no": "",
             "section": "A", "is_header": False, "description": "Butterfly valve 150 NB",
             "remark": "", "unit": "Nos", "area_qty": {}, "total_qty": 4.0,
             "supply_base_rate": None, "supply_escalation_pct": None,
             "supply_rate": 1000.0, "supply_amount": 4000.0,
             "supply_hsn": "", "supply_gst_rate": 18.0,
             "install_base_rate": None, "install_escalation_pct": None,
             "install_rate": 100.0, "install_amount": 400.0,
             "install_sac": "", "install_gst_rate": 18.0},
            {"line_id": "bbbbbbbbbbbb", "item_no": "2", "parent_item_no": "",
             "section": "A", "is_header": False, "description": "MS pipe 150 mm",
             "remark": "", "unit": "Mtrs", "area_qty": {}, "total_qty": 10.0,
             "supply_base_rate": None, "supply_escalation_pct": None,
             "supply_rate": 200.0, "supply_amount": 2000.0,
             "supply_hsn": "73069090", "supply_gst_rate": 18.0,
             "install_base_rate": None, "install_escalation_pct": None,
             "install_rate": None, "install_amount": None,
             "install_sac": "995461", "install_gst_rate": 18.0},
        ],
        "supply_subtotal": 6000.0, "install_subtotal": 400.0, "subtotal": 6400.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "", "rate_basis_label": "Base Rate",
    }
    lines = [
        {"name": "Butterfly valve 150 NB", "part_no": "BV-150", "hsn": "",
         "qty": 4.0, "unit": "Nos", "price": 1000.0, "total": 4000.0, "depth": 0},
        {"name": "MS pipe 150 mm", "part_no": "PIPE-150", "hsn": "73069090",
         "qty": 10.0, "unit": "Mtrs", "price": 200.0, "total": 2000.0, "depth": 0},
    ]
    STORE["proformas"]["hf-pi"] = printable({
        "id": "hf-pi", "ref": "PI-0901", "date": "2026-10-29",
        "quotation_id": "", "quotation_ref": "", "account_name": "Acme Contractors",
        "to": "Acme Contractors", "line_items": [dict(r) for r in lines],
        "subtotal": 6000.0, "grand_total": 7080.0, "tax_type": "exempt",
        "tax_info": {"total": 0.0}, "place_of_supply": "Maharashtra (27)",
        "company_branch": "", "auth_signatory": "", "payment_terms": "", "notes": "",
    })
    STORE["invoices"]["hf-ti"] = printable({
        "id": "hf-ti", "ref": "SF/TI/26-27/0901", "fy": "26-27",
        "date": "2026-10-29", "proforma_id": "hf-pi", "proforma_ref": "PI-0901",
        "account_name": "Acme Contractors", "to": "Acme Contractors",
        "line_items": [dict(r) for r in lines],
        "subtotal": 6000.0, "grand_total": 7080.0, "tax_type": "exempt",
        "tax_info": {"total": 0.0}, "place_of_supply": "Maharashtra (27)",
        "reverse_charge": False, "company_branch": "", "auth_signatory": "",
        "payment_terms": "", "notes": "", "status": "",
    })
    # ⚠ NOT `printable()`. That marks a record APPROVED, and
    #   `approval.can_modify()` refuses to reprice an approved order even with
    #   the ladder switched off — "a decision already taken is never
    #   overturned". A plain Draft is what the reprice form is for.
    STORE["purchases"]["hf-po"] = ({
        "id": "hf-po", "ref": "SF/PO/26-27/0901", "fy": "26-27",
        "date": "2026-10-29", "status": "Draft", "vendor_name": "Sant Valves",
        "to": "Sant Valves", "line_items": [dict(r) for r in lines],
        "extra_lines": [], "charges": [], "subtotal": 6000.0,
        "taxable_value": 6000.0, "grand_total": 6000.0, "tax_type": "exempt",
        "tax_info": {"total": 0.0}, "total_qty": 14.0,
        "company_branch": "", "auth_signatory": "", "notes": "",
    })
    return {"bid": "hf-boq", "pid": "hf-pi", "iid": "hf-ti", "oid": "hf-po"}


def _form(client, url):
    """The fill page's own POST body, read off the page it renders."""
    import re
    page = client.get(url).get_data(as_text=True)
    keys = re.findall(r'name="k" value="([^"]+)"', page)
    data = {"k": keys}
    for k in keys:
        fp = re.search(rf'name="fp_{re.escape(k)}" value="([^"]*)"', page).group(1)
        cur = re.search(rf'name="v_{re.escape(k)}" value="([^"]*)"', page).group(1)
        data[f"fp_{k}"] = fp
        data[f"v_{k}"] = cur
    return page, data


# ═══ 4. The tax invoice — an ISSUED document, blanks only ═══════════════════

def test_an_issued_tax_invoice_fills_a_blank_and_the_fill_prints(client):
    ids = _seed_chain(client)
    url = f"/invoice/hsn/{ids['iid']}"
    page, data = _form(client, url)
    assert page.count('name="v_li:') == 2
    data["v_li:0"] = "84818030"
    r = client.post(url, data=data)
    assert r.status_code == 302
    assert "updated+on+1+line." in r.headers["Location"]
    assert STORE["invoices"]["hf-ti"]["line_items"][0]["hsn"] == "84818030"
    sheet = client.get(f"/invoice/view/{ids['iid']}").get_data(as_text=True)
    assert '<td class="c-hsn">84818030</td>' in sheet


def test_an_issued_tax_invoice_refuses_a_changed_code_and_writes_nothing(client):
    ids = _seed_chain(client)
    url = f"/invoice/hsn/{ids['iid']}"
    _page, data = _form(client, url)
    data["v_li:0"] = "84818030"        # a legitimate fill, beside the refused one
    data["v_li:1"] = "11111111"        # was 73069090, printed
    r = client.post(url, data=data)
    assert r.status_code == 302
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "already printed as 73069090" in body
    rows = STORE["invoices"]["hf-ti"]["line_items"]
    assert rows[1]["hsn"] == "73069090", "the printed code stands"
    assert rows[0]["hsn"] == "", (
        "NOTHING is written on a refusal — not even the fill that would have "
        "been accepted on its own")
    assert HF.TRAIL_FIELD not in STORE["invoices"]["hf-ti"]


def test_the_printed_code_is_drawn_read_only_with_its_reason(client):
    ids = _seed_chain(client)
    page = client.get(f"/invoice/hsn/{ids['iid']}").get_data(as_text=True)
    assert page.count("readonly title=\"Already printed") == 1
    assert "printed &mdash; read-only" in page


def test_every_fill_on_an_issued_document_goes_on_its_trail(client):
    """A1: *"who, when, line, value"*."""
    ids = _seed_chain(client)
    url = f"/invoice/hsn/{ids['iid']}"
    _page, data = _form(client, url)
    data["v_li:0"] = "84818030"
    client.post(url, data=data)
    trail = HF.trail_of(STORE["invoices"]["hf-ti"])
    assert len(trail) == 1
    e = trail[0]
    assert e["value"] == "84818030" and e["code"] == "HSN"
    assert e["label"] == "BV-150" and e["line"] == "1"
    from conftest import TEST_USER
    assert e["by"] == TEST_USER, e
    assert len(e["at"]) == 16, "YYYY-MM-DD HH:MM"
    body = client.get(url).get_data(as_text=True)
    assert "Codes filled on this document" in body and "84818030" in body


def test_a_cancelled_tax_invoice_is_refused(client):
    ids = _seed_chain(client)
    STORE["invoices"]["hf-ti"]["status"] = "cancelled"
    r = client.get(f"/invoice/hsn/{ids['iid']}")
    assert r.status_code == 302
    assert "cancelled" in r.headers["Location"]
    r = client.post(f"/invoice/hsn/{ids['iid']}", data={"k": ["li:0"]})
    assert r.status_code == 302 and "cancelled" in r.headers["Location"]


def test_the_fill_page_reaches_no_figure(client):
    """
    It is the reason `fill_hsn()` needs no approval gate, and it is asserted on
    the running route rather than only on its source.
    """
    ids = _seed_chain(client)
    url = f"/invoice/hsn/{ids['iid']}"
    _page, data = _form(client, url)
    data.update({"v_li:0": "84818030", "price": "1", "qty": "999",
                 "total": "1", "grand_total": "1", "subtotal": "1",
                 "ref": "SF/TI/26-27/9999"})
    client.post(url, data=data)
    ti = STORE["invoices"]["hf-ti"]
    assert ti["ref"] == "SF/TI/26-27/0901"
    assert ti["grand_total"] == 7080.0 and ti["subtotal"] == 6000.0
    assert ti["line_items"][0]["price"] == 1000.0
    assert ti["line_items"][0]["qty"] == 4.0


# ═══ 5. A stale page cannot land a code on the wrong line ═══════════════════

def test_a_fingerprint_that_no_longer_matches_refuses_everything(client):
    ids = _seed_chain(client)
    url = f"/invoice/hsn/{ids['iid']}"
    _page, data = _form(client, url)
    data["v_li:0"] = "84818030"
    STORE["invoices"]["hf-ti"]["line_items"][0]["name"] = "Something else"
    r = client.post(url, data=data)
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "changed after the page was opened" in body
    assert STORE["invoices"]["hf-ti"]["line_items"][0]["hsn"] == ""


def test_a_key_that_is_not_on_the_document_refuses(client):
    ids = _seed_chain(client)
    r = client.post(f"/invoice/hsn/{ids['iid']}",
                    data={"k": ["li:99"], "fp_li:99": "x", "v_li:99": "7307"})
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "not on this document" in body


def test_a_key_the_form_did_not_carry_is_left_exactly_as_it_is(client):
    """A tab opened before a box existed — `purchase._reprice()`'s own rule."""
    ids = _seed_chain(client)
    r = client.post(f"/invoice/hsn/{ids['iid']}", data={})
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Nothing changed" in body
    rows = STORE["invoices"]["hf-ti"]["line_items"]
    assert rows[0]["hsn"] == "" and rows[1]["hsn"] == "73069090"


def test_a_code_is_capped_and_escaped_on_the_way_in(client):
    ids = _seed_chain(client)
    url = f"/invoice/hsn/{ids['iid']}"
    _page, data = _form(client, url)
    data["v_li:0"] = "<script>alert(1)</script>"
    client.post(url, data=data)
    # `HSN_MAX` is 8, and "<script>" is exactly 8 characters — so the cap
    # alone does not neutralise it and the ESCAPING is what has to.
    assert STORE["invoices"]["hf-ti"]["line_items"][0]["hsn"] == "<script>"
    sheet = client.get(f"/invoice/view/{ids['iid']}").get_data(as_text=True)
    assert "&lt;script&gt;" in sheet
    assert '<td class="c-hsn">&lt;script&gt;</td>' in sheet


# ═══ 6. The proforma — it feeds the NEXT invoice, never one already raised ══

def test_a_proforma_fill_reaches_the_next_invoice_and_not_one_already_raised(client):
    ids = _seed_chain(client)
    url = f"/proforma/hsn/{ids['pid']}"
    _page, data = _form(client, url)
    data["v_li:0"] = "84818030"
    assert client.post(url, data=data).status_code == 302
    assert STORE["proformas"]["hf-pi"]["line_items"][0]["hsn"] == "84818030"
    assert STORE["invoices"]["hf-ti"]["line_items"][0]["hsn"] == "", (
        "the tax invoice holds its OWN copy — CLIENT_CHANGES.md §1.2")
    # And the next invoice off this proforma takes it.
    r = client.get(f"/invoice/from/{ids['pid']}")
    assert r.status_code == 200
    assert "84818030" in r.get_data(as_text=True)


def test_a_proforma_is_treated_as_issued_and_takes_no_change(client):
    ids = _seed_chain(client)
    url = f"/proforma/hsn/{ids['pid']}"
    _page, data = _form(client, url)
    data["v_li:1"] = "11111111"
    r = client.post(url, data=data)
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "already printed as 73069090" in body
    assert STORE["proformas"]["hf-pi"]["line_items"][1]["hsn"] == "73069090"


# ═══ 7. The BOQ — two codes per line, blanks only, no figure touched ════════

def test_a_boq_line_offers_both_its_codes(client):
    ids = _seed_chain(client)
    page = client.get(f"/boq/hsn/{ids['bid']}").get_data(as_text=True)
    assert page.count('name="k" value="li:0:s"') == 1
    assert page.count('name="k" value="li:0:i"') == 1
    assert page.count('name="k" value="li:1:s"') == 1
    assert page.count('name="k" value="li:1:i"') == 1
    # Line 2 carries both codes already, so both of its boxes are read-only.
    assert page.count("readonly title=\"Already printed") == 2


def test_a_boq_fill_writes_both_codes_and_moves_no_figure(client):
    ids = _seed_chain(client)
    url = f"/boq/hsn/{ids['bid']}"
    _page, data = _form(client, url)
    data["v_li:0:s"] = "84818030"
    data["v_li:0:i"] = "995462"
    assert client.post(url, data=data).status_code == 302
    li = STORE["boqs"]["hf-boq"]["line_items"][0]
    assert li["supply_hsn"] == "84818030" and li["install_sac"] == "995462"
    # Not one figure moved. `supply_hsn`/`install_sac` are in no arithmetic.
    assert li["total_qty"] == 4.0 and li["supply_rate"] == 1000.0
    assert li["supply_amount"] == 4000.0 and li["install_amount"] == 400.0
    b = STORE["boqs"]["hf-boq"]
    assert (b["supply_subtotal"], b["install_subtotal"], b["subtotal"]) == (
        6000.0, 400.0, 6400.0)
    assert b["ref"] == "SF/BOQ/26-27/0901" and b["rev_no"] == 0
    assert len(STORE["boqs"]) == 1, "a fill is not a revision"


def test_a_boq_fill_refuses_a_change_and_names_which_code(client):
    ids = _seed_chain(client)
    url = f"/boq/hsn/{ids['bid']}"
    _page, data = _form(client, url)
    data["v_li:1:i"] = "995999"
    r = client.post(url, data=data)
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "(SAC)" in body and "already printed as 995461" in body
    assert STORE["boqs"]["hf-boq"]["line_items"][1]["install_sac"] == "995461"


def test_a_superseded_revision_is_refused(client):
    ids = _seed_chain(client)
    STORE["boqs"]["hf-boq-2"] = dict(STORE["boqs"]["hf-boq"],
                                     id="hf-boq-2", rev_no=1,
                                     supersedes="hf-boq")
    r = client.get(f"/boq/hsn/{ids['bid']}")
    assert r.status_code == 302 and "superseded" in r.headers["Location"]
    assert client.get("/boq/hsn/hf-boq-2").status_code == 200


def test_a_specification_header_offers_no_code(client):
    ids = _seed_chain(client)
    STORE["boqs"]["hf-boq"]["line_items"].insert(0, {
        "line_id": "cccccccccccc", "item_no": "A", "parent_item_no": "",
        "section": "A", "is_header": True, "description": "Clause text",
        "remark": "", "unit": "", "area_qty": {}, "total_qty": None})
    page = client.get(f"/boq/hsn/{ids['bid']}").get_data(as_text=True)
    assert "Clause text" not in page
    assert page.count('name="k" value=') == 4


def test_a_boq_fill_reaches_no_document_already_raised(client):
    """
    It is the snapshot rule, and it is what the page says in terms. An RA bill
    raised off this schedule keeps the code it was raised with.
    """
    ids = _seed_chain(client)
    STORE["ra_bills"]["hf-ra"] = printable({
        "id": "hf-ra", "ra_no": 1, "leg": "supply", "status": "issued",
        "boq_id": "hf-boq", "boq_ref": "SF/BOQ/26-27/0901", "boq_rev_no": 0,
        "date": "2026-10-29", "claims": [
            {"line_id": "aaaaaaaaaaaa", "item_no": "1", "section": "A",
             "description": "Butterfly valve 150 NB", "unit": "Nos",
             "hsn_sac": "", "gst_rate": 18.0, "approved_qty": 4.0,
             "approved_rate": 1000.0, "prev_qty": 0.0, "qty": 2.0,
             "rate": 1000.0, "amount": 2000.0, "balance_qty": 2.0,
             "rate_varies": False}],
    })
    url = f"/boq/hsn/{ids['bid']}"
    _page, data = _form(client, url)
    data["v_li:0:s"] = "84818030"
    client.post(url, data=data)
    assert STORE["ra_bills"]["hf-ra"]["claims"][0]["hsn_sac"] == ""


# ═══ 8. The RA bill — a DRAFT takes any code, an ISSUED one takes a blank ═══

def _seed_ra(status):
    STORE["ra_bills"]["hf-ra"] = printable({
        "id": "hf-ra", "ra_no": 1, "leg": "supply", "status": status,
        "boq_id": "hf-boq", "boq_ref": "SF/BOQ/26-27/0901", "boq_rev_no": 0,
        "date": "2026-10-29", "claims": [
            {"line_id": "aaaaaaaaaaaa", "item_no": "1", "section": "A",
             "description": "Butterfly valve 150 NB", "unit": "Nos",
             "hsn_sac": "", "gst_rate": 18.0, "approved_qty": 4.0,
             "approved_rate": 1000.0, "prev_qty": 0.0, "qty": 2.0,
             "rate": 1000.0, "amount": 2000.0, "balance_qty": 2.0,
             "rate_varies": False},
            {"line_id": "bbbbbbbbbbbb", "item_no": "2", "section": "A",
             "description": "MS pipe 150 mm", "unit": "Mtrs",
             "hsn_sac": "73069090", "gst_rate": 18.0, "approved_qty": 10.0,
             "approved_rate": 200.0, "prev_qty": 0.0, "qty": 5.0,
             "rate": 200.0, "amount": 1000.0, "balance_qty": 5.0,
             "rate_varies": False}],
    })
    return "hf-ra"


def test_a_draft_ra_bill_takes_any_code(client):
    _seed_chain(client)
    rid = _seed_ra("draft")
    url = f"/ra/hsn/{rid}"
    page, data = _form(client, url)
    assert "readonly title" not in page, "nothing is read-only on a draft"
    assert "still a <b>draft</b>" in page
    data["v_cl:0"] = "84818030"
    data["v_cl:1"] = "73079990"          # a CHANGE, legal on a draft
    assert client.post(url, data=data).status_code == 302
    cl = STORE["ra_bills"][rid]["claims"]
    assert cl[0]["hsn_sac"] == "84818030" and cl[1]["hsn_sac"] == "73079990"


def test_an_issued_ra_bill_fills_a_blank_and_refuses_a_change(client):
    _seed_chain(client)
    rid = _seed_ra("issued")
    url = f"/ra/hsn/{rid}"
    page, data = _form(client, url)
    assert page.count("readonly title=\"Already printed") == 1
    assert "only a <b>blank</b> code" in page
    data["v_cl:0"] = "84818030"
    assert client.post(url, data=data).status_code == 302
    assert STORE["ra_bills"][rid]["claims"][0]["hsn_sac"] == "84818030"
    _page, data = _form(client, url)
    data["v_cl:1"] = "11111111"
    r = client.post(url, data=data)
    body = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "already printed as 73069090" in body
    assert STORE["ra_bills"][rid]["claims"][1]["hsn_sac"] == "73069090"


def test_a_cancelled_ra_bill_is_refused(client):
    _seed_chain(client)
    rid = _seed_ra("cancelled")
    r = client.get(f"/ra/hsn/{rid}")
    assert r.status_code == 302 and "cancelled" in r.headers["Location"]


def test_an_ra_fill_moves_no_figure_and_prints(client):
    _seed_chain(client)
    rid = _seed_ra("issued")
    url = f"/ra/hsn/{rid}"
    _page, data = _form(client, url)
    data["v_cl:0"] = "84818030"
    client.post(url, data=data)
    cl = STORE["ra_bills"][rid]["claims"][0]
    assert (cl["qty"], cl["rate"], cl["amount"]) == (2.0, 1000.0, 2000.0)
    sheet = client.get(f"/ra/print/{rid}").get_data(as_text=True)
    assert '<td class="c-hsn">84818030</td>' in sheet


def test_the_merged_ra_shows_a_code_filled_on_its_source_bill(client):
    """
    ⚠ The merged RA holds no claims of its own and stacks its sources' rows at
    render, so it needs no page — stated as an assertion rather than left to
    the comment in `ra.fill_hsn()`.
    """
    import pathlib
    import merged_ra as MR
    assert "fill_hsn" not in dir(MR)
    assert "claims" not in MR.STORE.get("merged_ras", {}).get("x", {})
    src = pathlib.Path(MR.__file__).read_text(encoding="utf8")
    assert "stacked_rows(doc)" in src, (
        "the merged sheet must read its SOURCES' rows at render; the moment it "
        "holds claims of its own it needs a fill page and the over-claim guard "
        "counts a quantity twice")
    assert "HF.print_cell(" in src


# ═══ 9. The purchase order — the note, and the extra part's own rule ════════

def test_the_purchase_order_note_points_at_the_reprice_form(client):
    ids = _seed_chain(client)
    page = client.get(f"/purchase/view/{ids['oid']}").get_data(as_text=True)
    assert "HSN/SAC is missing on 1 line." in page
    assert f'href="/purchase/edit/{ids["oid"]}"' in page


def test_an_issued_orders_extra_part_keeps_its_printed_code(client):
    """
    ⚠ Matched on the DESCRIPTION, because `_parse_extra_lines()` re-reads that
    repeater whole and its rows are not positional.
    """
    ids = _seed_chain(client)
    po = STORE["purchases"][ids["oid"]]
    po["extra_lines"] = [{"description": "Gasket set", "unit": "Nos",
                          "qty": 2.0, "rate": 50.0, "total": 100.0,
                          "hsn": "40169390"}]
    po["status"] = "Issued"
    form = {"line_rate": ["1000", "200"], "line_discount": ["", ""],
            "extra_desc": ["Gasket set"], "extra_unit": ["Nos"],
            "extra_qty": ["2"], "extra_rate": ["50"], "extra_discount": [""],
            "extra_hsn": ["99999999"]}
    r = client.post(f"/purchase/edit/{ids['oid']}", data=form)
    assert r.status_code == 200
    assert "already printed as 40169390" in r.get_data(as_text=True)
    assert po["extra_lines"][0]["hsn"] == "40169390"


def test_an_issued_orders_extra_part_fills_a_blank(client):
    ids = _seed_chain(client)
    po = STORE["purchases"][ids["oid"]]
    po["extra_lines"] = [{"description": "Gasket set", "unit": "Nos",
                          "qty": 2.0, "rate": 50.0, "total": 100.0, "hsn": ""}]
    po["status"] = "Issued"
    r = client.post(f"/purchase/edit/{ids['oid']}", data={
        "line_rate": ["1000", "200"], "line_discount": ["", ""],
        "extra_desc": ["Gasket set"], "extra_unit": ["Nos"],
        "extra_qty": ["2"], "extra_rate": ["50"], "extra_discount": [""],
        "extra_hsn": ["40169390"]})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    assert po["extra_lines"][0]["hsn"] == "40169390"


def test_a_draft_orders_extra_part_takes_any_code(client):
    ids = _seed_chain(client)
    po = STORE["purchases"][ids["oid"]]           # Draft
    po["extra_lines"] = [{"description": "Gasket set", "unit": "Nos",
                          "qty": 2.0, "rate": 50.0, "total": 100.0,
                          "hsn": "40169390"}]
    r = client.post(f"/purchase/edit/{ids['oid']}", data={
        "line_rate": ["1000", "200"], "line_discount": ["", ""],
        "extra_desc": ["Gasket set"], "extra_unit": ["Nos"],
        "extra_qty": ["2"], "extra_rate": ["50"], "extra_discount": [""],
        "extra_hsn": ["99999999"]})
    assert r.status_code == 302
    assert po["extra_lines"][0]["hsn"] == "99999999"


def test_a_renamed_extra_part_is_not_matched_and_takes_what_was_typed(client):
    """A row that was re-described is not the same part, so there is no
    printed code for it to contradict."""
    ids = _seed_chain(client)
    po = STORE["purchases"][ids["oid"]]
    po["extra_lines"] = [{"description": "Gasket set", "unit": "Nos",
                          "qty": 2.0, "rate": 50.0, "total": 100.0,
                          "hsn": "40169390"}]
    po["status"] = "Issued"
    r = client.post(f"/purchase/edit/{ids['oid']}", data={
        "line_rate": ["1000", "200"], "line_discount": ["", ""],
        "extra_desc": ["Gasket set, viton"], "extra_unit": ["Nos"],
        "extra_qty": ["2"], "extra_rate": ["50"], "extra_discount": [""],
        "extra_hsn": ["99999999"]})
    assert r.status_code == 302
    assert po["extra_lines"][0]["hsn"] == "99999999"


# ═══ 10. The spec library — it fills blanks on lines raised LATER ═══════════

def _a_spec():
    """One clause from the library. `_fresh_store()` empties it per test."""
    import spec as SP
    SP.ensure_demo_specs()
    return next(iter(STORE["specs"]))


def test_a_spec_library_code_is_editable_on_its_own_form(client):
    """Already true before this pass, and asserted so it stays true."""
    sid = _a_spec()
    page = client.get(f"/spec/edit/{sid}").get_data(as_text=True)
    assert 'name="supply_hsn"' in page and 'name="install_sac"' in page


def test_a_spec_code_fills_a_boq_line_raised_AFTER_it_changed(client):
    """
    A1: *"A Spec Library HSN fills blanks on lines raised later. It never
    rewrites existing documents."*

    The BOQ's line editor copies the clause's codes onto a line **at pick
    time**, from the payload `_spec_catalog_json()` sends — so the clause as
    it stands when the BOQ is written is what the line carries, and a clause
    edited afterwards reaches nothing. Both halves fall out of that one fact,
    which is why this asserts on the payload (server-side, testable) and on
    `canFill`'s rule in the editor rather than on a function that does not
    exist.
    """
    sid = _a_spec()
    spec = STORE["specs"][sid]
    spec["supply_hsn"] = "84818030"
    spec["install_sac"] = "995462"
    payload = BQ._spec_catalog_json()
    assert '"supply_hsn": "84818030"' in payload
    assert '"install_sac": "995462"' in payload
    # The editor fills a BLANK only — `canFill()` is "never overwrites typed".
    src = pathlib.Path(BQ.__file__).read_text(encoding="utf8")
    assert "if (canFill(L, 'supply_hsn'))       setAuto(L, 'supply_hsn', sp.supply_hsn);" in src
    assert "if (canFill(L, 'install_sac'))      setAuto(L, 'install_sac', sp.install_sac);" in src


def test_a_spec_code_changed_later_reaches_no_boq_already_written(client):
    ids = _seed_chain(client)
    sid = _a_spec()
    STORE["specs"][sid]["supply_hsn"] = "99999999"
    li = STORE["boqs"][ids["bid"]]["line_items"]
    assert li[0]["supply_hsn"] == "" and li[1]["supply_hsn"] == "73069090"


# ═══ 11. Access — reuse, never a new permission ═════════════════════════════

NEW_ROUTES = ["boq.fill_hsn", "proforma.fill_hsn", "invoice.fill_hsn",
              "ra.fill_hsn"]


def test_every_new_route_is_classified_under_an_EXISTING_permission():
    existing = {"boq.fill_hsn": "boq.create",
                "proforma.fill_hsn": "proforma.create",
                "invoice.fill_hsn": "invoice.create",
                "ra.fill_hsn": "ra.edit"}
    for ep, perm in existing.items():
        assert auth.ROUTE_PERMISSIONS[ep] == perm
        assert perm in auth.PERMISSIONS, f"{perm} must already exist"


def test_no_permission_was_minted_for_this_pass():
    assert not [p for p in auth.PERMISSIONS if "hsn" in p.lower()]


def test_a_role_without_the_permission_is_refused_every_fill_route(client):
    """And refused on the POST, not only shown no button."""
    ids = _seed_chain(client)
    hr = auth.find_user("hsn-hr") or auth.create_user(
        "hsn-hr", "HR", "x-Pass-1234", ["role-hr"], created_by="test")
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = hr["id"]
    for url in (f"/boq/hsn/{ids['bid']}", f"/proforma/hsn/{ids['pid']}",
                f"/invoice/hsn/{ids['iid']}"):
        assert client.get(url).status_code == 403, url
        assert client.post(url, data={}).status_code == 403, url


def test_the_button_is_drawn_only_for_a_reader_the_gate_admits(client):
    ids = _seed_chain(client)
    owner_page = client.get(f"/invoice/view/{ids['iid']}").get_data(as_text=True)
    assert f'/invoice/hsn/{ids["iid"]}' in owner_page
    hr = auth.find_user("hsn-hr2") or auth.create_user(
        "hsn-hr2", "HR", "x-Pass-1234", ["role-hr"], created_by="test")
    assert not auth.can_reach("invoice.fill_hsn", hr)
    assert auth.can_reach("invoice.fill_hsn", auth.find_user("tester"))
