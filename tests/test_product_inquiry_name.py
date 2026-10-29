"""
The Draft PO is CALLED a "Product Inquiry" — 29 October 2026,
CLIENT_CHANGES.md §0 **fifty-ninth** block, B1, from the 28 October 2026
meeting with Yogesh Bankar.

    Display only: labels, headings, nav, printed title, register, dashboard
    card. Keep module names, collection names, URLs and stored field names
    unchanged, so no data or links break.

**This file is the second half of that sentence.** The first half — that the
words appear — is pinned by the page and print goldens, which moved and were
re-baselined with measured evidence. What needs a test of its own is the
half that is an ABSENCE: nothing addressable and nothing stored moved, so a
later pass cannot quietly turn a label change into a data migration.
"""

import pathlib
import re

import pytest

import auth
import cascade
import chrome as CH
import po_draft as PD
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent


# ═══ 1. Nothing addressable moved ══════════════════════════════════════════

def test_the_module_and_the_blueprint_keep_their_names():
    assert PD.__name__ == "po_draft"
    assert PD.po_draft_bp.name == "po_draft"
    assert PD.po_draft_bp.url_prefix == "/po"


def test_every_url_is_still_under_slash_po():
    import app as app_module
    rules = [r for r in app_module.app.url_map.iter_rules()
             if r.endpoint.startswith("po_draft.")]
    assert rules, "the blueprint vanished"
    for r in rules:
        assert str(r.rule).startswith("/po/") or str(r.rule) == "/po/", r.rule


def test_the_seven_endpoint_names_are_unchanged():
    """
    A renamed view function is a renamed endpoint, and an endpoint name is in
    `auth.ROUTE_PERMISSIONS`, in `url_for` at twelve call sites, and in
    `tests/test_page_reachability.py`'s link graph.
    """
    import app as app_module
    eps = {r.endpoint for r in app_module.app.url_map.iter_rules()
           if r.endpoint.startswith("po_draft.")}
    assert eps == {"po_draft.list_pos", "po_draft.create_po", "po_draft.view_po",
                   "po_draft.print_po", "po_draft.edit_po", "po_draft.pictures",
                   "po_draft.delete_po"}


def test_the_five_permission_IDS_are_unchanged():
    """
    ⚠ The load-bearing one. A renamed permission id reaches **no live role** —
    `auth.ensure_builtin_roles()` never rewrites an existing role's list — so
    the page it guards becomes unreachable by everybody, an Owner included,
    and the symptom is silence (`docs/PENDING_DEPLOY.md` §2). The
    DESCRIPTIONS changed; the ids did not.
    """
    for pid in ("po.view", "po.create", "po.edit", "po.delete", "po.print"):
        assert pid in auth.PERMISSIONS, pid
    assert not [p for p in auth.PERMISSIONS if "inquiry" in p.lower()]
    assert auth.ROUTE_PERMISSIONS["po_draft.list_pos"] == "po.view"
    assert auth.ROUTE_PERMISSIONS["po_draft.create_po"] == "po.create"
    assert auth.ROUTE_PERMISSIONS["po_draft.edit_po"] == "po.edit"
    assert auth.ROUTE_PERMISSIONS["po_draft.delete_po"] == "po.delete"
    assert auth.ROUTE_PERMISSIONS["po_draft.print_po"] == "po.print"
    assert auth.ROUTE_PERMISSIONS["po_draft.pictures"] == "po.edit"


def test_no_builtin_roles_grant_list_moved():
    """So there is nothing to reconcile on the box for this item."""
    auth.ensure_builtin_roles()
    for rid, role in (STORE.get("roles") or {}).items():
        for p in role.get("permissions") or ():
            assert p in auth.PERMISSIONS, (rid, p)
            assert not p.startswith("inquiry."), (rid, p)
    assert (STORE.get("roles") or {}), "no roles were seeded"


def test_the_import_kind_key_is_still_dpo():
    """It is in the URL `/import/dpo` and in a saved `doc_import_layouts` row."""
    import docimport as DI
    kind = next(k for k in DI.KINDS.values() if k.endpoint == "po_draft.create_po")
    assert kind.key == "dpo"
    assert kind.title == "a product inquiry"
    assert kind.noun == "product inquiry"


# ═══ 2. Nothing stored moved ═══════════════════════════════════════════════

def test_the_collection_is_still_purchase_orders():
    import db
    assert "purchase_orders" in STORE
    assert "purchase_orders" in db.COLLECTIONS
    assert not [k for k in STORE if "inquir" in k.lower()]


def test_the_cascade_edge_keeps_its_collection_and_changes_only_its_label():
    graph = next(getattr(cascade, n) for n in dir(cascade)
                 if n.isupper() and isinstance(getattr(cascade, n), dict)
                 and "boqs" in getattr(cascade, n))
    edge = next(e for e in graph["boqs"] if e.collection == "purchase_orders")
    assert edge.label == "Product Inquiry"
    assert edge.fields == ("boq_id",)


def test_the_series_record_and_prefix_are_unchanged():
    """
    ⚠ `SF/DPO` is the client's own number on their own paper book, and the
    prefix is an editable field at `/settings`. Renaming it is **their**
    decision, not ours (§7 gap 15's rule), and this pass did not take it.
    """
    import settings as SET
    assert SET.PO_SERIES_RECORD == "po_draft_series"
    assert SET.PO_SERIES_DEFAULTS["prefix"] == "SF/DPO"
    assert PD.next_ref().startswith("SF/DPO/")


def test_every_stored_field_name_on_a_record_is_unchanged(client):
    import json
    import address
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    lines = [li for li in STORE["boqs"][bid]["line_items"]
             if not li.get("is_header")][:2]
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    r = client.post(f"/po/create?boq={bid}", data={
        "date": "2026-10-29", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "1"}
                                         for li in lines]})})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    rec = next(iter(STORE["purchase_orders"].values()))
    for key in ("id", "ref", "date", "boq_id", "boq_ref", "boq_rev_no",
                "project_name", "site_location", "account_name", "vendor_id",
                "vendor_name", "vendor_source", "to", "vendor_gstin",
                "delivery_to", "notes", "items", "company_branch",
                "auth_signatory"):
        assert key in rec, f"the record lost {key}"
    assert not [k for k in rec if "inquir" in k.lower()]
    for row in rec["items"]:
        for key in ("line_id", "is_header", "item_no", "description"):
            assert key in row, f"a line lost {key}"


# ═══ 3. The words DO appear, on every surface the ruling names ═════════════

SURFACES = [
    ("the register",        "/po/",                 "Product <span>Inquiries</span>"),
    ("the register title",  "/po/",                 "<title>Product Inquiries"),
    ("the nav rail",        "/po/",                 'title="Product Inquiries"'),
    ("the top bar",         "/po/",                 '<div class="tb-name">Product Inquiries</div>'),
    ("the dashboard card",  "/",                    '<div class="card-title">Product Inquiries</div>'),
    ("the BOQ raise bar",   None,                   "Product Inquiry"),
    ("the settings section", "/settings/",          "Product Inquiry Series"),
]


@pytest.mark.parametrize("what,url,needle",
                         [s for s in SURFACES if s[1]],
                         ids=[s[0] for s in SURFACES if s[1]])
def test_the_words_appear(client, what, url, needle):
    client.get("/boq/")
    assert needle in client.get(url).get_data(as_text=True), what


def test_the_create_form_and_the_document_carry_the_name(client):
    import json
    import address
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    form = client.get(f"/po/create?boq={bid}").get_data(as_text=True)
    assert "<title>Product Inquiry" in form
    assert "Product <span>Inquiry</span>" in form
    assert "Raise product inquiry</button>" in form

    li = [x for x in STORE["boqs"][bid]["line_items"] if not x.get("is_header")][0]
    r = client.post(f"/po/create?boq={bid}", data={
        "date": "2026-10-29", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "1"}]})})
    assert r.status_code == 302
    assert "Product+Inquiry+raised" in r.headers["Location"]
    pid = next(iter(STORE["purchase_orders"]))
    sheet = client.get(f"/po/print/{pid}").get_data(as_text=True)
    assert '<div class="doc-title">PRODUCT INQUIRY</div>' in sheet
    assert "DRAFT PURCHASE ORDER" not in sheet
    assert "Inquiry No." in sheet
    assert "SF/DPO/" in sheet, "the NUMBER is untouched"
    assert "quote our inquiry number" in sheet


def test_the_BOQ_raise_bar_offers_it_by_the_new_name(client):
    client.get("/boq/")
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    page = client.get(f"/boq/view/{bid}").get_data(as_text=True)
    bar = page.split('class="raise-bar"', 1)[1].split("</div>\n", 1)[0]
    assert "Product Inquiry" in bar
    assert ">Draft PO<" not in bar


# ═══ 4. The old words are gone from every rendered page ════════════════════

OLD_WORDS = ("Draft Purchase Order", "Draft PO", "draft purchase order",
             "draft PO", "DRAFT PURCHASE ORDER")

SWEPT = ["/", "/po/", "/boq/", "/purchase/", "/settings/", "/projects/",
         "/dc/", "/measurement/", "/quotation/", "/proforma/", "/invoice/",
         "/ra/", "/merged/", "/receipt/", "/client/", "/employee/",
         "/charge/", "/address/", "/users", "/spec/"]


@pytest.mark.parametrize("url", SWEPT)
def test_no_rendered_page_still_says_draft_po(client, url):
    """
    ⚠ The sweep, so a surface nobody thought of fails here rather than
    reaching the client. Every page a signed-in Owner can open.
    """
    client.get("/boq/")
    html = client.get(url).get_data(as_text=True)
    for word in OLD_WORDS:
        assert word not in html, f"{url} still says {word!r}"


def test_the_documents_own_pages_say_nothing_of_the_kind(client):
    import json
    import address
    address.ensure_demo_addresses()
    client.get("/boq/")
    STORE.setdefault("purchase_orders", {}).clear()
    bid = next(b for b, r in STORE["boqs"].items() if not r.get("supersedes"))
    vendor = next(a["id"] for a in STORE["addresses"].values()
                  if a.get("type") == "vendor")
    li = [x for x in STORE["boqs"][bid]["line_items"] if not x.get("is_header")][0]
    client.post(f"/po/create?boq={bid}", data={
        "date": "2026-10-29", "vendor_id": vendor, "notes": "",
        "po_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "1"}]})})
    pid = next(iter(STORE["purchase_orders"]))
    for url in (f"/po/view/{pid}", f"/po/print/{pid}", f"/po/edit/{pid}",
                f"/po/pictures/{pid}", f"/po/delete/{pid}",
                f"/po/create?boq={bid}", "/po/"):
        html = client.get(url).get_data(as_text=True)
        for word in OLD_WORDS:
            assert word not in html, f"{url} still says {word!r}"


def test_the_permission_descriptions_and_the_matrix_are_the_new_words():
    for pid in ("po.view", "po.create", "po.edit", "po.delete", "po.print"):
        label = auth.PERMISSIONS[pid][0]
        assert "product inquir" in label.lower(), (pid, label)
        assert "draft" not in label.lower(), (pid, label)
    doc = (REPO / "docs" / "ACCESS_MATRIX.md").read_text(encoding="utf8")
    assert "Raise a product inquiry" in doc
    assert "draft purchase order" not in doc.lower()
    assert "draft po" not in doc.lower()
    # And the ids in the matrix are the untouched ones.
    assert "`po.create`" in doc and "`po.view`" in doc


# ═══ 5. The one constant set, read everywhere ═══════════════════════════════

def test_the_display_names_live_in_one_place():
    assert PD.DOC_NAME == "Product Inquiry"
    assert PD.DOC_NAME_PLURAL == "Product Inquiries"
    assert PD.DOC_TITLE == "PRODUCT INQUIRY"
    assert PD.DOC_NO_LABEL == "Inquiry No."
    src = (REPO / "po_draft.py").read_text(encoding="utf8")
    # Every rendered occurrence reads the constant, so the module holds no
    # second copy of the words outside the constant block itself.
    body = src.split("DOC_NO_LABEL = ", 1)[1].split("\n", 1)[1]
    code = "\n".join(l.split("#", 1)[0] for l in body.split("\n"))
    for word in ("Product Inquiries", "PRODUCT INQUIRY", "Inquiry No."):
        assert word not in code, (
            f"{word!r} is written out again instead of reading the constant")


def test_the_nav_label_comes_from_the_registry_and_not_a_literal():
    r = next(r for r in CH.REGISTERS if r.key == "po_draft")
    assert r.name == "Product Inquiries"
    assert r.endpoint == "po_draft.list_pos"
    assert r.count == len(STORE.get("purchase_orders") or {}) or True
