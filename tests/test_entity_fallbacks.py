"""
HTML entities used as empty-value fallbacks must not be escaped.

The bug: `esc(value or '&mdash;')` puts the entity INSIDE the escaper, so its
`&` becomes `&amp;` and the browser prints the literal text "&mdash;" where an
em-dash belongs. It was visible in the spec library's HSN/SAC column. The
correct shape is `esc(value or '') or '&mdash;'` — the fallback substituted
AFTER escaping, so only the value is ever escaped.

`&mdash;` for "nothing here" is house style in ~30 places across the repo, so
this is a mistake any of them can make, and one an author cannot see in the
source: `esc(x or '&mdash;')` and `esc(x or '') or '&mdash;'` read almost the
same. The check has to be on the rendered page.

Hence one assertion over every page the app serves rather than a spec-specific
one. `&amp;mdash;` in a response body is never correct here — no seeded record
and nothing these builders write contains the text "&mdash;", so the only way
those five characters reach a page is an entity that went through `esc()`.

There was no existing all-routes-render-200 test to extend — the suite's 200
assertions are per-module — so the route list is derived from `app.url_map`
and every rule must be either exercised or named in SKIP with a reason. A new
route cannot quietly escape the check by being forgotten here.
"""

import pytest

import address
import demo_data as DD
import pipeline as P
import ra
import spec
from store import STORE

# The escaped entity. Written as two pieces so this file cannot match its own
# source if somebody greps the repo for the literal instead of rendering.
BROKEN = "&amp;" + "mdash;"


# ── Rules that are deliberately not fetched ────────────────────────────────

SKIP = {
    # ⚠ `/spec/delete`, `/product/delete` and `/address/delete` used to sit here,
    # skipped because a GET to any of them destroyed the record the rest of the
    # sweep was about to render. All three are now GET-confirms with POST
    # destroys, so they render a real page and are swept like everything else —
    # which is exactly the property their removal from this list asserts.
    #
    # Flask registers this automatically. ABOUT.md §1: there is no /static
    # folder — every asset is a base64 data URI — so it can only 404.
    "/static/<path:filename>": "no /static folder exists; assets are data URIs",
    # `/setup` renders only while `users` is empty and redirects once one
    # exists. Every fixture here signs in, so a user always exists and this can
    # only ever be a 302. That self-disabling is the point of the route and is
    # asserted directly in tests/test_auth.py::test_setup_disables_itself.
    # `/login` is NOT skipped — it renders a real form and is swept normally.
    "/setup": "renders only while no user exists; the fixtures all sign in",
}


# ── The two records that actually provoke the bug ──────────────────────────
#
# A fallback entity only renders where a value is MISSING, and all 56 seeded
# clauses carry an HSN, a SAC and a unit. Without these the sweep would pass
# against the unfixed code, because it would never reach the branch.
#
# Two of them, because spec.py writes the unit fallback twice — once in the
# unsized branch and once in the per-variant loop — and one record can only be
# on one side of that `if`.

BLANK_FORM = {
    "category": "Piping", "spec_text": "Regression fixture — deliberately blank.",
    "supply_hsn": "", "install_sac": "",
    "supply_gst_rate": "18", "install_gst_rate": "18",
    "var_dimension": [""], "var_dim_unit": [""],
    "var_supply": [""], "var_install": [""],
}

BLANK_SPECS = {
    # code -> the variant rows that put it in the branch we want
    "REG-BLANK-UNSIZED": {"var_label": [""], "var_unit": [""]},
    "REG-BLANK-SIZED":   {"var_label": ["100mm"], "var_unit": [""]},
}


@pytest.fixture()
def populated(client):
    """
    One store with a record in every collection a page can render.

    Every route below has to return a real page, not an empty state: an empty
    list page renders no rows, and a row is exactly where a fallback entity
    appears. The control test at the foot of this file proves the sweep is
    really looking at populated pages.
    """
    client.get("/boq/")          # seeds the 56 specs and the demo BOQ
    address.ensure_demo_addresses()
    from product import ensure_demo_products
    ensure_demo_products()
    client.get("/settings/")     # seeds the company identity

    blank = {}
    for code, variant_rows in BLANK_SPECS.items():
        r = client.post("/spec/add",
                        data=dict(BLANK_FORM, code=code, title=f"{code} fixture",
                                  **variant_rows))
        assert r.status_code == 302, f"{code} was rejected: {r.get_data(as_text=True)[:500]}"
        blank[code] = spec.spec_by_code(code)["id"]

    qid = _a_quotation()

    r = client.post(f"/proforma/from/{qid}",
                    data={"date": "2026-08-04", "advance_pct": "100"})
    assert r.status_code == 302, "the PI was not created"
    pid = next(iter(STORE["proformas"]))

    r = client.post(f"/invoice/from/{pid}", data={
        "date": "2026-08-04", "place_of_supply": "Maharashtra",
        "advance_received": "0"})
    assert r.status_code == 302, "the tax invoice was not created"
    iid = next(iter(STORE["invoices"]))

    vendor = next(a for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    r = client.post("/purchase/create", data={
        "date": "2026-08-04", "vendor_id": vendor["id"], "status": "Draft",
        "tax_type": "exempt", "line_product_id": [next(iter(STORE["products"]))],
        "line_qty": ["2"], "line_rate": ["500"]})
    assert r.status_code == 302, "the purchase order was not created"

    bid = DD.BOQ_META["id"]
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()
    # TWO bills, and the split matters. A bill with money receipted against it
    # cannot be deleted (`ra.can_delete`) — deleting it would orphan the
    # payment — so `/ra/delete/<id>` would redirect rather than render if the
    # only bill were the paid one. RA1 carries the receipt and feeds the
    # /receipt/* rules; RA2 is the latest and unpaid, which is what makes the
    # edit, delete, issue and cancel confirmations render a page for the sweep.
    #
    # RA1 is **issued** and RA2 is a **draft**, and that is not decoration: a
    # receipt may only be recorded against an issued bill (`ra.can_receipt`), so
    # a draft RA1 with money against it would be a fixture asserting a state the
    # app refuses to produce.
    paid_rid = _an_ra_bill(bid, ra_no=1, rid="r1-supply", ref="SF/RA/26-27/0001",
                           status="issued")
    rid = _an_ra_bill(bid, ra_no=2, rid="r2-supply", ref="SF/RA/26-27/0002",
                      status="draft")
    rcid = _a_receipt(paid_rid, bid)
    dpid = _a_draft_po(bid)
    dcid = _a_challan(bid)

    # `/product/delete` renders its confirmation page only for a product that
    # may actually be deleted; one locked into an assembly redirects with the
    # refusal instead, which is the guard working. Pick a deletable one so the
    # sweep is checking the page rather than the redirect.
    import product as product_mod
    deletable_pid = next(pid_ for pid_ in STORE["products"]
                         if product_mod.can_delete_product(pid_)[0])

    bid2 = "boq2-no-bills"
    STORE["boqs"][bid2] = dict(STORE["boqs"][bid])
    STORE["boqs"][bid2]["id"] = bid2

    STORE.setdefault("projects", {})["proj-1"] = {
        "id": "proj-1", "name": "Test Project", "norm_name": "test project",
        "client": "", "site_address": "", "notes": "", "created_at": "2026-08-16T12:00:00Z"
    }
    STORE.setdefault("charges", {})["ch-1"] = {
        "id": "ch-1", "date": "2026-08-16", "person": "Test Person", "head": "Travel",
        "description": "Test", "project_id": "proj-1", "project_name": "Test Project",
        "taxable_amount": 100.0, "gst_rate": 0.0, "gst_amount": 0.0,
        "notes": "", "created_at": "2026-08-16T12:00:00Z", "updated_at": "2026-08-16T12:00:00Z"
    }

    # A second user for the /users/* confirmations to act on. Deliberately not
    # the logged-in Owner: deactivating the only Owner is refused, and the
    # refusal page is not the markup this sweep is checking.
    import auth
    auth.ensure_builtin_roles()
    spare = auth.find_user("sweep-spare") or auth.create_user(
        "sweep-spare", "", "sweep-spare-pw", ["role-hr"], created_by="fixture")
    spare_uid = spare["id"]

    yield {
        "ids": {
            "/address/delete/<id>": next(iter(STORE["addresses"])),
            "/address/edit/<id>":   next(iter(STORE["addresses"])),
            # The access-control pages. `spare_uid` is a second, ordinary user
            # so that `/users/deactivate` renders its confirmation rather than
            # the "this is the only Owner" refusal — both are real pages, but
            # only the confirmation exercises the row markup the sweep is
            # looking at. `role-hr` is a builtin role with a small permission
            # set, so the editor renders every checkbox block quickly.
            "/users/edit/<id>":       spare_uid,
            "/users/deactivate/<id>": spare_uid,
            "/users/activate/<id>":   spare_uid,
            "/roles/edit/<id>":       "role-hr",
            "/boq/print/<id>":      bid,
            "/boq/view/<id>":       bid,
            "/charge/delete/<id>":  "ch-1",
            "/charge/edit/<id>":    "ch-1",
            "/client/edit-party/<id>": bid2,
            "/invoice/from/<pid>":  pid,
            "/invoice/view/<id>":   iid,
            "/product/delete/<id>": deletable_pid,
            "/product/view/<id>":   next(iter(STORE["products"])),
            "/projects/delete/<id>": "proj-1",
            "/projects/edit/<id>":   "proj-1",
            "/projects/view/<id>":   "proj-1",
            "/proforma/from/<qid>": qid,
            "/proforma/view/<id>":  pid,
            "/purchase/view/<id>":  next(iter(STORE["purchases"])),
            # The two BOQ-side create forms. Both render a populated page: the
            # first the whole 97-line picker with a rate box per line, the
            # second the draft's own rows — and `_a_draft_po` deliberately
            # leaves `vendor_name` blank, which is exactly the cell that falls
            # back to the house em-dash.
            "/purchase/from-boq/<boq_id>":     bid,
            "/purchase/from-draft/<draft_id>": dpid,
            "/quotation/view/<id>": qid,
            "/ra/delete/<id>":      rid,
            "/ra/edit/<id>":        rid,
            # RA2 is the draft, so both lifecycle confirmations render a page
            # rather than redirecting with a refusal. `/ra/issue` needs a bill
            # that is not already issued; `/ra/cancel` needs one that is neither
            # cancelled nor carrying receipts — RA1 is the paid one and would
            # bounce on the second count.
            "/ra/issue/<id>":       rid,
            "/ra/cancel/<id>":      rid,
            "/ra/print/<id>":       rid,
            "/ra/view/<id>":        rid,
            "/po/delete/<id>":      dpid,
            "/po/edit/<id>":        dpid,
            "/po/print/<id>":       dpid,
            "/po/view/<id>":        dpid,
            "/dc/delete/<id>":      dcid,
            "/dc/edit/<id>":        dcid,
            "/dc/print/<id>":       dcid,
            "/dc/view/<id>":        dcid,
            "/receipt/delete/<id>": rcid,
            "/receipt/edit/<id>":   rcid,
            "/spec/delete/<id>":    blank["REG-BLANK-UNSIZED"],
            "/spec/edit/<id>":      blank["REG-BLANK-UNSIZED"],
            "/spec/view/<id>":      blank["REG-BLANK-UNSIZED"],
        },
        # The second spec's pages, which the id map above has no room for: one
        # rule, two records, and the sized one is the other half of the `if`.
        "extra": [f"/spec/view/{blank['REG-BLANK-SIZED']}",
                  f"/spec/edit/{blank['REG-BLANK-SIZED']}"],
        "blank": blank,
    }

    STORE["ra_bills"].clear()
    STORE["receipts"].clear()
    STORE.setdefault("purchase_orders", {}).clear()
    STORE.setdefault("delivery_challans", {}).clear()
    STORE.setdefault("projects", {}).clear()
    STORE.setdefault("charges", {}).clear()


def _a_challan(boq_id: str) -> str:
    """
    One delivery challan **with rows on it**, so the sweep has a document.

    `dispatch_to` and `po_no` are deliberately left blank: those cells are
    exactly where the register and the document fall back to the house em-dash,
    which is the branch this file exists to check. `_a_draft_po` leaves
    `vendor_name` blank for the same reason.
    """
    cid = "dc-1"
    line = next(li for li in STORE["boqs"][boq_id]["line_items"]
                if not li["is_header"] and li["total_qty"] > 0)
    STORE.setdefault("delivery_challans", {})[cid] = {
        "id": cid, "ref": "54", "date": "2026-08-16",
        "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "project_name": "Sify Bangalore", "site_location": "",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "consignee_id": "", "consignee_source": "typed",
        "consignee_name": "Samruddhi Fire", "consignee_addr": "",
        "consignee_phone": "",
        "dispatch_mode": "Transport", "dispatch_to": "",
        "po_no": "", "po_date": "", "notes": "",
        "items": [{"line_id": line["line_id"], "is_header": False,
                   "item_no": line["item_no"],
                   "description": line["description"],
                   "unit": line["unit"], "qty": float(line["total_qty"])}],
        "company_branch": "", "auth_signatory": "",
    }
    return cid


def _a_draft_po(boq_id: str) -> str:
    """
    One draft PO **with rows on it**, so the sweep has a document to look at.

    ⚠ This fixture used to write `"items": []`. The whole contract of this file
    is that every route renders a *populated* page — "an empty list page renders
    no rows, and a row is exactly where a fallback entity appears" — so an empty
    draft PO let `/po/view` and `/po/print` pass over the branch this sweep
    exists to check. `vendor_name` is deliberately blank on one of the two
    documents' cells for the same reason `_a_receipt` leaves `instrument_ref`
    blank: that cell is where the register falls back to the house em-dash.
    """
    pid = "po-draft-1"
    line = next(li for li in STORE["boqs"][boq_id]["line_items"]
                if not li["is_header"] and li["total_qty"] > 0)
    STORE.setdefault("purchase_orders", {})[pid] = {
        "id": pid, "ref": "SF/DPO/0001",
        "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "project_name": "Sify Bangalore", "site_location": "",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "date": "2026-08-15",
        "vendor_id": "", "vendor_name": "", "vendor_source": "typed",
        "to": "", "vendor_gstin": "",
        "delivery_to": "", "notes": "",
        "items": [{"line_id": line["line_id"], "is_header": False,
                   "item_no": line["item_no"],
                   "description": line["description"],
                   "unit": line["unit"], "qty": float(line["total_qty"]),
                   "pcs": ""}],
        "company_branch": "", "auth_signatory": "",
    }
    return pid

def _a_quotation() -> str:
    """A minimal but well-formed quotation — enough to raise a PI against."""
    import uuid
    qid = str(uuid.uuid4())
    q = {
        "id": qid, "ref": "QT-9001", "date": "2026-08-04",
        "account_name": "Test Contractor Pvt Ltd", "contact_person": "",
        "to": "Test Contractor Pvt Ltd\nMumbai", "bill_gstin": "",
        "bill_state": "Maharashtra", "ship_same": "on",
        "line_items": [{"type": "item", "name": "MS pipe", "part_no": "P-1",
                        "hsn": "73063090", "qty": 10.0, "unit": "Mtrs",
                        "price": 1000.0, "total": 10000.0, "depth": 0}],
        "subtotal": 10000.0, "tax_type": "exempt", "tax_info": {"total": 0.0},
        "grand_total": 10000.0, "total_qty": 10.0,
    }
    P.ensure_fields(q)
    STORE["quotations"][qid] = q
    return qid


def _an_ra_bill(boq_id: str, ra_no: int = 1, rid: str = "r1-supply",
                ref: str = "SF/RA/26-27/0001", status: str = "draft") -> str:
    """One claim against the demo BOQ, so /ra/view and /boq/view have a bill."""
    li = next(li for li in STORE["boqs"][boq_id]["line_items"]
              if not li["is_header"] and li["total_qty"] > 0)
    claims = [ra.build_claim(li, 1.0, li["supply_rate"], 0.0, li["supply_rate"])]
    subtotal, drows, dtotal, net = ra.bill_totals(claims, [])
    STORE["ra_bills"][rid] = {
        "id": rid, "ref": ref, "fy": "26-27",
        "date": "2026-08-06", "boq_id": boq_id, "boq_ref": "SF/BOQ/26-27/0001",
        "boq_rev_no": 0, "ra_no": ra_no, "leg": "supply", "claims": claims,
        "claim_subtotal": subtotal, "deductions": drows,
        "deduction_total": dtotal, "net_payable": net,
        "status": status, "issued_on": "", "cancelled_on": "",
        "cancel_reason": "", "notes": "",
    }
    return rid


def _a_receipt(ra_id: str, boq_id: str) -> str:
    """
    One payment against that bill, so /receipt/edit and /receipt/delete render.

    `instrument_ref` is deliberately blank: that cell is exactly where the
    receipts table falls back to the house em-dash, so a fixture that filled it
    would let the sweep pass over the branch this file exists to check.
    """
    rcid = "rc1"
    STORE["receipts"][rcid] = {
        "id": rcid, "ref": "SF/RCPT/26-27/0001", "fy": "26-27",
        "date": "2026-08-07", "ra_id": ra_id, "ra_ref": "SF/RA/26-27/0001",
        "ra_no": 1, "leg": "supply", "boq_id": boq_id,
        "boq_ref": "SF/BOQ/26-27/0001", "project_name": "Sify",
        "account_name": "Test Contractor Pvt Ltd", "amount": 1000.0,
        "mode": "neft", "instrument_ref": "", "instrument_date": "",
        "notes": "",
    }
    return rcid


def _urls(populated):
    """Every GET rule in the app, with its parameters filled in."""
    import app as app_module

    ids = populated["ids"]
    urls, uncovered = [], []
    for rule in sorted(app_module.app.url_map.iter_rules(), key=lambda r: r.rule):
        if "GET" not in rule.methods or rule.rule in SKIP:
            continue
        if not rule.arguments:
            # /ra/create and /po/create are parameterless forms that still need a query
            # string; without it there is no schedule to claim/draft against.
            if rule.rule == "/ra/create":
                urls.append(rule.rule + f"?boq={DD.BOQ_META['id']}&leg=supply")
            elif rule.rule in ("/po/create", "/dc/create"):
                urls.append(rule.rule + f"?boq={DD.BOQ_META['id']}")
            else:
                urls.append(rule.rule)
        elif rule.rule in ids:
            placeholder = rule.rule[rule.rule.index("<"):rule.rule.rindex(">") + 1]
            urls.append(rule.rule.replace(placeholder, ids[rule.rule]))
        else:
            uncovered.append(rule.rule)

    assert not uncovered, (
        f"these routes take an id and are neither exercised nor in SKIP: "
        f"{uncovered}. Add an id to the `populated` fixture, or a reason to "
        f"SKIP — a route that renders nowhere here is a route this check "
        f"cannot protect.")
    return urls + populated["extra"]


# ═══ CLASS: an HTML entity escaped by the thing meant to escape user text ══

def test_no_page_prints_an_escaped_entity(populated, client):
    """
    `esc('&mdash;')` is `&amp;mdash;`, which the browser draws as the seven
    characters "&mdash;" instead of an em-dash. Fixed in spec.py at the HSN/SAC
    cell and at both "Measured In" cells; asserted here for every page, because
    the same one-character slip works anywhere the house dash is used.
    """
    for url in _urls(populated):
        r = client.get(url)
        assert r.status_code == 200, f"{url} did not render"
        body = r.get_data(as_text=True)
        assert BROKEN not in body, (
            f"{url} printed a literal '&mdash;': an entity was passed INTO "
            f"esc(). Write it as esc(value or '') or '&mdash;' — fallback "
            f"outside the escaper, as at spec.py:998.")


def test_the_swept_pages_really_do_use_the_fallback(populated, client):
    """
    The control. The assertion above is "something is NOT on the page", which
    passes just as well against a page that renders no rows at all — or against
    a repo where somebody replaced every `&mdash;` with a literal dash and left
    the test green over a convention it no longer guards.

    This proves the entity is genuinely being emitted, unescaped, on exactly
    the pages that carry the three fixed cells: the library list (HSN/SAC) and
    both spec views (Measured In, once per branch of the unsized `if`).
    """
    blank = populated["blank"]
    pages = ["/spec/"] + [f"/spec/view/{sid}" for sid in blank.values()]
    for url in pages:
        body = client.get(url).get_data(as_text=True)
        assert "&mdash;" in body, f"{url} emitted no fallback entity at all"
        assert BROKEN not in body
