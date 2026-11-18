"""
The purchase order's "Deliver to" picker — 18 November 2026 hotfix.

A `<select>` of the address book sits directly above the free-text Deliver-to
box on every PO form (create, from-BOQ / from-Product-Inquiry, edit). Picking
an address FILLS the box in the browser; the box stays the snapshot that
prints. `deliver_to_address_id` is stored beside it only while the posted text
is still exactly the picked address's formatted text.

What this file holds:

  * the picker is on create and edit, every active type offered, grouped,
    site / office / delivery first;
  * archived addresses are not offered — except the one an order already
    holds, shown "(archived)" and selected;
  * picking + saving stores text and id; text edited after picking stores a
    blank id; an id that is not in the book is ignored and the text kept;
  * an order written before the picker (no key) renders, edits and prints
    unchanged, and a plain re-save adds no key;
  * a poisoned company name is escaped in the option label and in the script;
  * a login holding only purchase permissions (no `address.view`) sees it.
"""

import re

import pytest

import address
import auth
import purchase as PU
from store import STORE

from test_po_make import ORDER, _only, shop  # noqa: F401

SITE = "dt-site-1"
OFFICE = "dt-office-1"
SHIP = "dt-ship-1"
BILL = "dt-bill-1"
ODD = "dt-odd-1"
GONE = "dt-archived-1"


def _addr(aid, label, atype, **kw):
    rec = {"id": aid, "label": label, "type": atype, "contact_name": "",
           "company": kw.pop("company", label + " Co"), "line1": "Plot 7",
           "line2": "", "landmark": "", "city": kw.pop("city", "Pune"),
           "state": "Maharashtra", "pincode": "411001", "country": "India",
           "phone": "", "email": "", "gstin": ""}
    rec.update(kw)
    STORE["addresses"][aid] = rec
    return rec


@pytest.fixture()
def book(client, shop):  # noqa: F811
    STORE.setdefault("purchases", {}).clear()
    for aid in list(STORE["addresses"]):
        if aid.startswith("dt-"):
            del STORE["addresses"][aid]
    _addr(SITE, "Chakan Site", "site")
    _addr(OFFICE, "Head Office", "office")
    _addr(SHIP, "Bhosari Store", "shipping")
    _addr(BILL, "Billing Desk", "billing")
    _addr(ODD, "Filed Oddly", "not-a-type")
    _addr(GONE, "Old Yard", "site", active=False)
    yield shop
    for aid in list(STORE["addresses"]):
        if aid.startswith("dt-"):
            del STORE["addresses"][aid]
    STORE["purchases"].clear()


def _text(aid):
    return "\n".join(address.format_address_lines(STORE["addresses"][aid]))


def _create(client, **over):
    data = dict(ORDER, extra_desc=["Gasket", "", ""], extra_qty=["1", "", ""],
                extra_rate=["10", "", ""])
    data.update(over)
    r = client.post("/purchase/create", data=data)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return _only("purchases")


def _select(html):
    m = re.search(r'<select id="deliver_to_address_id"[^>]*>(.*?)</select>', html, re.S)
    assert m, "the Deliver-to picker is not on the page"
    return m.group(1)


def _groups(sel):
    return re.findall(r'<optgroup label="([^"]*)">', sel)


# ══ The picker on the forms ═══════════════════════════════════════════════

def test_create_form_has_the_picker_above_the_textarea_with_grouped_options(client, book):
    html = client.get("/purchase/create").get_data(as_text=True)
    sel = _select(html)
    assert html.index('id="deliver_to_address_id"') < html.index('<textarea id="delivery_to"')
    assert '<option value="">Pick saved address</option>' in sel
    groups = _groups(sel)
    assert groups[:3] == ["Project Site", "Office", "Delivery"]
    for g in ("Billing", "Vendor", "Other"):
        assert g in groups, g
    for aid in (SITE, OFFICE, SHIP, BILL, ODD):
        assert f'value="{aid}"' in sel, aid
    assert " selected" not in sel, "the create form preselects nothing"
    assert "Old Yard" not in sel, "an archived address is not offered"
    # The default prefill is today's.
    assert "Bhosari Store Co" not in html.split('<textarea id="delivery_to"')[1][:400]
    # Filling dispatches `input` so the autosave catches it.
    assert 'dispatchEvent(new Event("input", { bubbles: true }))' in html


def test_the_other_create_forms_and_edit_carry_it_too(client, book):
    po = _create(client)
    for url in (f"/purchase/edit/{po['id']}", f"/purchase/from-boq/{book['boq']}"):
        html = client.get(url).get_data(as_text=True)
        sel = _select(html)
        assert _groups(sel)[:3] == ["Project Site", "Office", "Delivery"], url


def test_the_existing_address_picker_order_is_unchanged_for_other_callers(client, book):
    plain = address.picker_options()
    assert _groups(plain)[:2] == ["Office", "Project Site"]


# ══ Storage ═══════════════════════════════════════════════════════════════

def test_picking_and_saving_stores_the_text_and_the_id(client, book):
    # The browser posts a textarea with CRLF.
    po = _create(client, deliver_to_address_id=SITE,
                 delivery_to=_text(SITE).replace("\n", "\r\n"))
    assert po["deliver_to_address_id"] == SITE
    assert po["delivery_to"].replace("\r\n", "\n") == _text(SITE)


def test_text_edited_after_picking_stores_a_blank_id(client, book):
    po = _create(client, deliver_to_address_id=SITE,
                 delivery_to=_text(SITE) + "\nGate 3, ask for Ravi")
    assert po["deliver_to_address_id"] == ""
    assert po["delivery_to"].endswith("Gate 3, ask for Ravi")


def test_free_text_stores_a_blank_id(client, book):
    po = _create(client, delivery_to="Our stores")
    assert po["deliver_to_address_id"] == ""
    assert po["delivery_to"] == "Our stores"


def test_a_bogus_id_is_ignored_and_the_text_kept(client, book):
    po = _create(client, deliver_to_address_id="no-such-address",
                 delivery_to="Typed by hand")
    assert po["deliver_to_address_id"] == ""
    assert po["delivery_to"] == "Typed by hand"


def test_an_archived_id_cannot_be_picked_on_create(client, book):
    po = _create(client, deliver_to_address_id=GONE, delivery_to=_text(GONE))
    assert po["deliver_to_address_id"] == ""


def test_from_boq_stores_the_pick(client, book):
    import json
    line = book["lines"][0]
    r = client.post(f"/purchase/from-boq/{book['boq']}", data=dict(
        ORDER, deliver_to_address_id=SHIP, delivery_to=_text(SHIP),
        po_json=json.dumps({"lines": [{"line_id": line["line_id"], "qty": "1",
                                       "rate": "100"}]})))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    po = _only("purchases")
    assert po["deliver_to_address_id"] == SHIP
    assert po["delivery_to"] == _text(SHIP)


# ══ Edit ══════════════════════════════════════════════════════════════════

def _edit_form(po, **over):
    data = {"date": po["date"], "vendor_id": po["vendor_id"], "quotation_id": "",
            "tax_type": po["tax_type"], "cgst_rate": "9", "igst_rate": "18",
            "delivery_to": po.get("delivery_to", ""), "notes": "", "note": "",
            "round_off_present": "1", "round_off": "1",
            # One blank row: `line_k` present is what makes this the FULL
            # editor's POST rather than the legacy reprice.
            "line_k": [""], "line_pick": [""], "line_hdr": [""], "line_name": [""],
            "line_part": [""], "line_make": [""], "line_hsn": [""], "line_qty": [""],
            "line_unit": [""], "line_rate": [""], "line_discount": [""],
            "extra_desc": ["Gasket"], "extra_qty": ["1"], "extra_rate": ["10"],
            "extra_unit": ["Nos"]}
    data.update(over)
    return data


def test_edit_shows_the_stored_pick_and_resaves_it(client, book):
    po = _create(client, deliver_to_address_id=OFFICE, delivery_to=_text(OFFICE))
    sel = _select(client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True))
    assert f'<option value="{OFFICE}" selected>' in sel
    r = client.post(f"/purchase/edit/{po['id']}", data=_edit_form(
        po, deliver_to_address_id=SITE, delivery_to=_text(SITE)))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert po["deliver_to_address_id"] == SITE and po["delivery_to"] == _text(SITE)
    r = client.post(f"/purchase/edit/{po['id']}", data=_edit_form(
        po, deliver_to_address_id=SITE, delivery_to="One-off yard"))
    assert r.status_code == 302
    assert po["deliver_to_address_id"] == "" and po["delivery_to"] == "One-off yard"


def test_an_archived_stored_address_is_shown_marked_and_selected(client, book):
    po = _create(client, deliver_to_address_id=SITE, delivery_to=_text(SITE))
    STORE["addresses"][SITE]["active"] = False
    sel = _select(client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True))
    assert f'<option value="{SITE}" selected>Chakan Site — Pune (archived)</option>' in sel
    assert "Old Yard" not in sel, "only the stored archived address is offered"
    # And a re-save keeps it, because it is the one the order holds.
    r = client.post(f"/purchase/edit/{po['id']}", data=_edit_form(
        po, deliver_to_address_id=SITE, delivery_to=_text(SITE)))
    assert r.status_code == 302
    assert po["deliver_to_address_id"] == SITE


def _legacy(client):
    """An order exactly as written before the picker: no key at all."""
    po = _create(client, delivery_to="Our stores, Bhosari")
    del po["deliver_to_address_id"]
    return po


def test_an_old_order_without_the_key_edits_unchanged(client, book):
    po = _legacy(client)
    html = client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True)
    assert " selected" not in _select(html)
    assert ">Our stores, Bhosari</textarea>" in html
    before = set(po)
    r = client.post(f"/purchase/edit/{po['id']}", data=_edit_form(po))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert "deliver_to_address_id" not in po, "a plain re-save adds no key"
    assert set(po) - before <= {"edit_log"}
    view = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "Our stores, Bhosari" in view and "deliver_to_address_id" not in view


def test_an_old_order_whose_text_is_one_address_preselects_it_display_only(client, book):
    po = _legacy(client)
    po["delivery_to"] = _text(SHIP)
    keys = set(po)
    sel = _select(client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True))
    assert f'<option value="{SHIP}" selected>' in sel
    assert set(po) == keys, "a GET writes nothing"


def test_two_addresses_with_the_same_text_preselect_neither(client, book):
    po = _legacy(client)
    _addr("dt-twin", "Twin", "site", company="Bhosari Store Co")
    po["delivery_to"] = _text(SHIP)
    assert _text("dt-twin") == _text(SHIP)
    sel = _select(client.get(f"/purchase/edit/{po['id']}").get_data(as_text=True))
    assert " selected" not in sel


def test_the_print_never_shows_the_picker(client, book):
    po = _create(client, deliver_to_address_id=SITE, delivery_to=_text(SITE))
    html = client.get(f"/purchase/view/{po['id']}").get_data(as_text=True)
    assert "deliver_to_address_id" not in html and "Pick saved address" not in html


# ══ Escaping ══════════════════════════════════════════════════════════════

def test_a_poisoned_company_and_label_are_escaped(client, book):
    _addr("dt-evil", '<img src=x onerror=alert(1)>', "site",
          company='</script><script>alert(2)</script>', city='"><b>c</b>')
    html = client.get("/purchase/create").get_data(as_text=True)
    sel = _select(html)
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in sel
    assert "&#34;&gt;&lt;b&gt;c&lt;/b&gt;" in sel or "&quot;&gt;&lt;b&gt;c&lt;/b&gt;" in sel
    assert "</script><script>alert(2)" not in html


# ══ Permissions ═══════════════════════════════════════════════════════════

def test_a_purchase_only_login_sees_and_uses_the_picker(client, book):
    auth.ensure_builtin_roles()
    STORE["roles"]["role-dt-buyer"] = {
        "id": "role-dt-buyer", "name": "DT Buyer", "builtin": False,
        "permissions": ["purchase.view", "purchase.create", "purchase.edit"]}
    existing = auth.find_user("dt-buyer")
    if existing:
        del STORE["users"][existing["id"]]
    user = auth.create_user("dt-buyer", "dt-buyer", "pw-dt-buyer-12345",
                            ["role-dt-buyer"], created_by="deliver-to-test")
    try:
        assert "address.view" not in auth.permissions_of(user)
        with client.session_transaction() as s:
            s[auth.SESSION_KEY] = user["id"]
        assert client.get("/address/").status_code in (302, 403)
        r = client.get("/purchase/create")
        assert r.status_code == 200
        assert f'value="{SITE}"' in _select(r.get_data(as_text=True))
        po = _create(client, deliver_to_address_id=SITE, delivery_to=_text(SITE))
        assert po["deliver_to_address_id"] == SITE
        r = client.get(f"/purchase/edit/{po['id']}")
        assert r.status_code == 200
        assert f'<option value="{SITE}" selected>' in _select(r.get_data(as_text=True))
    finally:
        del STORE["users"][user["id"]]
        del STORE["roles"]["role-dt-buyer"]
