"""
ABOUT.md §7 gap 38 — the PO form follows the catalogue switch too.

12 September 2026, CLIENT_CHANGES.md §0 twenty-eighth block, change 3. Two
halves, in this order, and the order is the point:

1. **A from-scratch purchase order of extra lines alone passes
   `purchase._parse_lines()`, ALWAYS** — not only while the catalogue is
   hidden. Until this date `_parse_lines()` refused an empty list with *"Add
   at least one item to the purchase order"*, which is what made the
   twenty-seventh block stop rather than point the item rows at the toggle:
   with no catalogue row to pick, a from-scratch order could not be raised at
   all. The rule is now `create_purchase()`'s and it is stated over BOTH kinds
   of line — an order with no catalogue line and no extra line is still
   refused. It holds whatever the switch says, because a validity rule that
   read a display switch would make the same order valid or invalid depending
   on the day you looked at it.

2. **Then** `_product_options()` and the `catalog_rates` embed read the
   switch: hidden → no catalogue rows. This was the one place in the
   application where catalogue items were still visible.

And every reader of a PO's lines copes with zero catalogue lines: create,
view / print (one route), edit, `job_cost()`, the quotation deal panel's
Committed figure, the project page and the register.

⚠ **No figure on an existing PO moves.** Nothing in the arithmetic changed
— `_totals_of()` already summed both kinds of line — and the pinned
`/purchase/view` golden in `tests/test_print_golden.py` did not move.
"""

import pytest
from werkzeug.datastructures import MultiDict

import address
import purchase as PU
from store import STORE

VENDOR_ID = "b2000006-face-4000-8000-000000000006"
PRODUCT_PID = "a1000001-beef-4000-8000-000000000001"


# ── the switch, both ways ───────────────────────────────────────────────────

@pytest.fixture(params=["hidden", "unhidden"])
def switch(request):
    """Run a test under BOTH states of the catalogue switch."""
    import auth
    saved = set(auth.HIDDEN_BLUEPRINTS)
    auth.HIDDEN_BLUEPRINTS.clear()
    if request.param == "hidden":
        auth.HIDDEN_BLUEPRINTS.add("product")
    try:
        yield request.param
    finally:
        auth.HIDDEN_BLUEPRINTS.clear()
        auth.HIDDEN_BLUEPRINTS.update(saved)


def _seed():
    from product import ensure_demo_products
    ensure_demo_products()
    address.ensure_demo_addresses()


def _form(*, items=(), extras=(), charges=(), qid="", project_id=""):
    """
    A `/purchase/create` post. `items` is `[(pid, qty, rate), ...]`, `extras`
    is `[(desc, unit, qty, rate), ...]`, `charges` is `[(label, amount), ...]`
    — every one taxable, as the form's default box is.
    """
    data = {
        "date": "2026-09-12", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0",
        "quotation_id": qid, "project_id": project_id,
        "line_product_id": [i[0] for i in items],
        "line_qty":        [str(i[1]) for i in items],
        "line_rate":       [str(i[2]) for i in items],
        "line_discount":   ["" for _ in items],
        "extra_desc":      [e[0] for e in extras],
        "extra_unit":      [e[1] for e in extras],
        "extra_qty":       [str(e[2]) for e in extras],
        "extra_rate":      [str(e[3]) for e in extras],
        "extra_discount":  ["" for _ in extras],
        "charge_label":    [c[0] for c in charges],
        "charge_amount":   [str(c[1]) for c in charges],
    }
    for n, _c in enumerate(charges):
        data[f"charge_taxable_{n}"] = "1"
    return data


def _post(client, **kw):
    _seed()
    return client.post("/purchase/create", data=_form(**kw))


def _newest_po():
    return list(STORE["purchases"].values())[-1]


def _error_of(response) -> str:
    body = response.get_data(as_text=True)
    assert 'class="alert alert-error"' in body, "the POST did not re-render with an error"
    return body


# ══ 1. _parse_lines: no catalogue line is not an error, ALWAYS ═════════════

def test_parse_lines_with_no_rows_returns_no_error_under_either_switch(switch):
    items, err = PU._parse_lines(MultiDict())
    assert (items, err) == ([], ""), (
        f"_parse_lines() refused an empty form with the catalogue {switch}: {err!r}")


def test_parse_lines_with_only_blank_rows_returns_no_error_under_either_switch(switch):
    form = MultiDict([("line_product_id", ""), ("line_qty", ""), ("line_rate", ""),
                      ("line_product_id", ""), ("line_qty", ""), ("line_rate", "")])
    assert PU._parse_lines(form) == ([], "")


def test_parse_lines_never_reads_the_switch():
    """
    The validity of a line list is not the display switch's business — read
    at AST level, so the rule cannot quietly come back as a branch.
    """
    import ast
    import inspect
    src = inspect.getsource(PU._parse_lines)
    tree = ast.parse(src)
    fn = tree.body[0]
    # the docstring RECORDS the old refusal; the code must not carry it
    code_only = ast.unparse(ast.Module(body=fn.body[1:], type_ignores=[]))
    assert "blueprint_hidden" not in code_only and "_catalogue_hidden" not in code_only
    assert "Add at least one" not in code_only
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "HIDDEN_BLUEPRINTS" not in names


def test_parse_lines_still_validates_a_real_row(switch):
    _seed()
    form = MultiDict([("line_product_id", PRODUCT_PID), ("line_qty", "0"), ("line_rate", "5")])
    items, err = PU._parse_lines(form)
    assert items == [] and "greater than zero" in err


# ══ 2. The route: extra lines alone are an order; no lines at all are not ═══

def test_an_order_of_extra_lines_alone_is_created_under_either_switch(client, switch):
    r = _post(client, extras=[("Bullet fastener 8mm", "Nos", 100, 12),
                              ("Cutting wheel 4 inch", "Nos", 20, 45)])
    assert r.status_code == 302, _error_of(r)[:400]
    po = _newest_po()
    assert po["line_items"] == []
    assert len(po["extra_lines"]) == 2
    assert po["subtotal"] == 2100.00
    assert po["taxable_value"] == 2100.00
    assert po["tax_info"]["CGST"] == 189.00 and po["tax_info"]["SGST"] == 189.00
    assert po["grand_total"] == 2478.00
    assert po["total_qty"] == 120.0


def test_an_order_with_no_line_of_either_kind_is_refused_under_either_switch(client, switch):
    before = len(STORE["purchases"])
    r = _post(client)
    assert r.status_code == 200
    assert PU.NO_LINES_ERROR in _error_of(r)
    assert len(STORE["purchases"]) == before


def test_a_charge_alone_is_not_an_order(client, switch):
    """A charge is what the vendor bills beyond the goods; with no goods it is nothing."""
    before = len(STORE["purchases"])
    r = _post(client, charges=[("Transport", 1500)])
    assert r.status_code == 200
    assert PU.NO_LINES_ERROR in _error_of(r)
    assert len(STORE["purchases"]) == before


def test_a_catalogue_line_alone_is_still_an_order(client, switch):
    """
    The rule is over both kinds of line, so the old case still passes — and
    it passes under BOTH switch states, because validity does not read the
    switch. A pid that reaches the server while the catalogue is hidden is
    still a product in the store; refusing it would be the day-dependent
    validity the twenty-eighth block rules out.
    """
    r = _post(client, items=[(PRODUCT_PID, 2, 1000)])
    assert r.status_code == 302, _error_of(r)[:400]
    po = _newest_po()
    assert len(po["line_items"]) == 1 and po["extra_lines"] == []
    assert po["subtotal"] == 2000.00


def test_the_extra_line_refusals_still_come_first(client, switch):
    """A malformed extra line is named before the no-lines rule is reached."""
    r = _post(client, extras=[("Something", "Nos", -1, 5)])
    assert r.status_code == 200
    body = _error_of(r)
    assert PU.NO_LINES_ERROR not in body


# ══ 3. The item rows follow the switch ══════════════════════════════════════

def test_product_options_offers_no_row_while_hidden(client):
    import auth
    _seed()
    saved = set(auth.HIDDEN_BLUEPRINTS)
    try:
        auth.HIDDEN_BLUEPRINTS.clear(); auth.HIDDEN_BLUEPRINTS.add("product")
        hidden = PU._product_options()
        auth.HIDDEN_BLUEPRINTS.clear()
        shown = PU._product_options()
    finally:
        auth.HIDDEN_BLUEPRINTS.clear(); auth.HIDDEN_BLUEPRINTS.update(saved)
    assert hidden == '<option value="">&#8212; select item &#8212;</option>'
    assert hidden.count("<option") == 1
    assert shown.count("<option") == 1 + len(STORE["products"])
    assert PRODUCT_PID in shown and PRODUCT_PID not in hidden


def test_the_create_page_draws_no_catalogue_row_or_rate_while_hidden(client):
    import auth
    _seed()
    saved = set(auth.HIDDEN_BLUEPRINTS)
    try:
        auth.HIDDEN_BLUEPRINTS.clear(); auth.HIDDEN_BLUEPRINTS.add("product")
        hidden = client.get("/purchase/create").get_data(as_text=True)
        auth.HIDDEN_BLUEPRINTS.clear()
        shown = client.get("/purchase/create").get_data(as_text=True)
    finally:
        auth.HIDDEN_BLUEPRINTS.clear(); auth.HIDDEN_BLUEPRINTS.update(saved)

    assert hidden.count("<option") > 0
    for pid, p in STORE["products"].items():
        assert pid not in hidden, f"{p['name']} is still offered while hidden"
        assert p["name"] not in hidden
    assert "var RATES = {};" in hidden
    assert "The product catalogue is switched off" in hidden
    assert "extra parts" in hidden

    assert PRODUCT_PID in shown
    assert "var RATES = {};" not in shown
    assert f'"{PRODUCT_PID}":' in shown
    assert "The product catalogue is switched off" not in shown


def test_the_shipped_configuration_is_hidden_and_the_form_still_writes_an_order(client):
    """The end-to-end shape on the shipped toggle: no rows, and an order goes through."""
    import auth
    assert auth.blueprint_hidden("product")
    r = _post(client, extras=[("Welding rod 3.15mm", "Kg", 5, 300)])
    assert r.status_code == 302, _error_of(r)[:400]
    assert _newest_po()["line_items"] == []


def test_the_reprice_form_offers_no_catalogue_row_either(client):
    """`/purchase/edit/<id>` re-prices stored rows and never reads the catalogue."""
    assert _post(client, extras=[("Welding rod 3.15mm", "Kg", 5, 300)]).status_code == 302
    po = _newest_po()
    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert PRODUCT_PID not in html and 'name="line_product_id"' not in html


# ══ 4. Every reader copes with zero catalogue lines ═════════════════════════

@pytest.fixture()
def extras_only_po(client):
    _seed()
    # a quotation to link the order to, so the deal panel has a figure to draw
    STORE["quotations"]["q-gap38"] = {
        "id": "q-gap38", "ref": "QT-3800", "date": "2026-09-01",
        "account_name": "Gap 38 Customer", "contact_person": "", "to": "Gap 38 Customer",
        "tax_type": "cgst_sgst", "cgst_rate": 9.0, "sgst_rate": 9.0, "igst_rate": 18.0,
        "vat_rate": 5.0, "tax_info": {"CGST": 900.0, "SGST": 900.0, "total": 1800.0,
                                      "cgst_rate": 9.0, "sgst_rate": 9.0},
        "subtotal": 10000.0, "grand_total": 11800.0, "total_qty": 1.0,
        "selections": [], "line_items": [
            {"type": "item", "name": "Quoted thing", "part_no": "QT-1", "hsn": "8413",
             "qty": 1.0, "unit": "Nos", "price": 10000.0, "total": 10000.0, "depth": 0}],
    }
    import pipeline as P
    P.ensure_fields(STORE["quotations"]["q-gap38"])
    STORE.setdefault("projects", {})["proj-gap38"] = {
        "id": "proj-gap38", "name": "Gap 38 Project", "norm_name": "gap 38 project",
        "client": "Gap 38 Customer", "notes": "", "created_at": "", "updated_at": "",
        "site_address_id": "", "site_address": "",
    }
    r = _post(client, extras=[("Bullet fastener 8mm", "Nos", 100, 12),
                              ("Cutting wheel 4 inch", "Nos", 20, 45)],
              qid="q-gap38", project_id="proj-gap38")
    assert r.status_code == 302
    po = _newest_po()
    yield po
    STORE["quotations"].pop("q-gap38", None)
    STORE["projects"].pop("proj-gap38", None)


def test_view_and_print_render_the_extra_lines_and_the_totals(client, extras_only_po):
    po = extras_only_po
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert po["ref"] in html
    assert "Bullet fastener 8mm" in html and "Cutting wheel 4 inch" in html
    assert "2,100.00" in html and "2,478.00" in html
    # the print-blanking block is B7's and is not the question here; the
    # sheet's own structural markers are what says it rendered
    assert '<div class="items-wrap">' in html


def test_the_register_lists_it(client, extras_only_po):
    html = client.get("/purchase/").get_data(as_text=True)
    assert extras_only_po["ref"] in html


def test_edit_reprices_the_extra_lines_with_no_item_row_to_post(client, extras_only_po):
    po = extras_only_po
    assert client.get(f"/purchase/edit/{po['id']}").status_code == 200
    r = client.post(f"/purchase/edit/{po['id']}", data={
        "extra_desc": ["Bullet fastener 8mm"], "extra_unit": ["Nos"],
        "extra_qty": ["100"], "extra_rate": ["15"], "extra_discount": [""],
    })
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:400]
    assert po["line_items"] == []
    assert len(po["extra_lines"]) == 1
    assert po["subtotal"] == 1500.00
    assert po["grand_total"] == 1770.00


def test_job_cost_and_the_deal_panel_carry_the_extra_lines_as_committed(client, extras_only_po):
    jc = PU.job_cost("q-gap38")
    assert jc["count"] == 1
    assert jc["committed"] == 2478.00
    assert jc["extra_committed"] == 2100.00 and jc["extra_count"] == 2
    html = client.get("/quotation/view/q-gap38").get_data(as_text=True)
    assert "Of which, extra parts" in html
    assert "2,478" in html


def test_the_project_page_lists_it_with_its_total(client, extras_only_po):
    html = client.get("/projects/view/proj-gap38").get_data(as_text=True)
    assert extras_only_po["ref"] in html
    assert "2,478" in html


def test_from_boq_with_nothing_ticked_is_still_refused(client):
    """The BOQ picker's own empty rule is untouched — it reads the schedule, not the catalogue."""
    import boq as BQ
    BQ.ensure_demo_specs() if hasattr(BQ, "ensure_demo_specs") else None
    BQ.ensure_demo_boq()
    _seed()
    boq_id = next(iter(STORE["boqs"]))
    r = client.post(f"/purchase/from-boq/{boq_id}", data={
        "date": "2026-09-12", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "cgst_sgst", "cgst_rate": "9", "igst_rate": "0"})
    assert r.status_code == 200
    assert "No lines are ticked" in r.get_data(as_text=True)
    assert len(STORE["purchases"]) == 0


# ══ 5. No figure on an existing PO moves ════════════════════════════════════

def test_totals_of_reproduces_a_stored_order_with_both_kinds_of_line():
    items = [{"type": "item", "name": "x", "part_no": "x", "hsn": "", "qty": 2.0,
              "unit": "Nos", "price": 1000.0, "discount_pct": 0.0, "total": 2000.0, "depth": 0}]
    extras = [{"type": "extra", "description": "y", "unit": "Nos", "qty": 3.0,
               "rate": 10.0, "discount_pct": 0.0, "total": 30.0, "rate_is_assumed": False}]
    sub, taxable, tax, grand, qty = PU._totals_of(items, "cgst_sgst", 9.0, 0.0, [], extras)
    assert (sub, taxable, grand, qty) == (2030.0, 2030.0, 2395.4, 5.0)
    sub, taxable, tax, grand, qty = PU._totals_of([], "cgst_sgst", 9.0, 0.0, [], extras)
    assert (sub, taxable, grand, qty) == (30.0, 30.0, 35.4, 3.0)
    sub, taxable, tax, grand, qty = PU._totals_of(items, "cgst_sgst", 9.0, 0.0, [], [])
    assert (sub, taxable, grand, qty) == (2000.0, 2000.0, 2360.0, 2.0)
