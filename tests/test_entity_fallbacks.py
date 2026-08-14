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
    # edit and delete confirmations render a page for the sweep to look at.
    paid_rid = _an_ra_bill(bid, ra_no=1, rid="r1-supply", ref="SF/RA/26-27/0001")
    rid = _an_ra_bill(bid, ra_no=2, rid="r2-supply", ref="SF/RA/26-27/0002")
    rcid = _a_receipt(paid_rid, bid)

    # `/product/delete` renders its confirmation page only for a product that
    # may actually be deleted; one locked into an assembly redirects with the
    # refusal instead, which is the guard working. Pick a deletable one so the
    # sweep is checking the page rather than the redirect.
    import product as product_mod
    deletable_pid = next(pid_ for pid_ in STORE["products"]
                         if product_mod.can_delete_product(pid_)[0])

    yield {
        "ids": {
            "/address/delete/<id>": next(iter(STORE["addresses"])),
            "/address/edit/<id>":   next(iter(STORE["addresses"])),
            "/boq/print/<id>":      bid,
            "/boq/view/<id>":       bid,
            "/invoice/from/<pid>":  pid,
            "/invoice/view/<id>":   iid,
            "/product/delete/<id>": deletable_pid,
            "/product/view/<id>":   next(iter(STORE["products"])),
            "/proforma/from/<qid>": qid,
            "/proforma/view/<id>":  pid,
            "/purchase/view/<id>":  next(iter(STORE["purchases"])),
            "/quotation/view/<id>": qid,
            "/ra/delete/<id>":      rid,
            "/ra/edit/<id>":        rid,
            "/ra/certify/<id>":     rid,
            "/ra/print/<id>":       rid,
            "/ra/view/<id>":        rid,
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
                ref: str = "SF/RA/26-27/0001") -> str:
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
        "status": "draft", "certified_on": "", "notes": "",
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
            # /ra/create is the one parameterless form that still needs a query
            # string; without it there is no schedule to claim against.
            urls.append(rule.rule + (f"?boq={DD.BOQ_META['id']}&leg=supply"
                                     if rule.rule == "/ra/create" else ""))
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
