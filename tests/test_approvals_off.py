"""
The approval ladder, switched OFF in code — 12 September 2026.

CLIENT_CHANGES.md §0, the twenty-eighth block, change 4: 3B.05–3B.07 are
deferred under MG/SF/2026-06 as sequencing, the ladder returns after a trial
period, and measurement approval goes off with it by the owner's decision.
`approval.LADDER_ON = False` is the switch, `approval.ladder_on()` the one
accessor, and this file is the OFF state — every existing approval, B7, B8 and
measurement-cap test runs with the switch ON through `conftest.ladder_on` and
is untouched, so the ladder goes on being proved for the day it returns.

What OFF means, and what each section proves:

1. every approve/reject route is refused for all seven roles, both verbs, with
   nothing written — a signed-in user gets the switched-off page, a stranger
   the ordinary login bounce;
2. no queue, tile, chip or band renders;
3. a PENDING record, a grandfathered one and one raised while OFF print and
   download; edit and delete follow the document's own status rules;
4. a decision already taken is never overturned — APPROVED and REJECTED
   records behave exactly as today;
5. the DRAFT overprint and a CANCELLED bill print again, as before B7;
6. `/roles` draws every `*.approve` box disabled, labelled *switched off*, and
   freezes the grant both ways;
7. THE TRAP — the measurement cap still binds: a saved sheet is the ceiling,
   a claim above it is refused, C1 is satisfied by a saved sheet and still
   refuses with none, and `ra.py`'s `{}`-means-grandfather path never fires
   for a project that has sheets;
8. every record created while OFF is STAMPED at create, never inferred;
9. when the switch goes back ON: a raised-while-off record is not gated and
   shows its mark; a record raised while ON is gated; a record that was
   PENDING before the switch went off carries no mark and returns to pending.

The cap, the `{}` path and the stamp are each mutation-proved: the guard is
replaced by its pre-switch reading and the assertion that would have caught
the defect is shown to fail.
"""

import copy
import json

import pytest

import approval
import auth
import boq as BQ
import dashboard
import measurement as MS
import ra
from store import STORE

from conftest import charge_form
from test_approval import _a_charge, _as, _user, cast  # noqa: F401
from test_approval_b7 import _a_bill, _where
from test_measurement import only_sheet, payload, priced, raise_sheet, seeded  # noqa: F401
from test_merged_ra import chain, pair  # noqa: F401

ROLE_SLUGS = ("owner", "director", "operation-head", "hr", "sales-manager",
              "purchase-manager", "accountant")

# `(doc_key, a record builder)` — one per entry in `approval.DOCUMENTS`, so a
# document added to the table without a row here fails the sweep below.
def _a_measurement(mid="off-ms", **over):
    rec = {"id": mid, "ref": "SF/MS/26-27/0001", "fy": "26-27", "date": "2026-09-12",
           "boq_id": f"boq-{mid}", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
           "project_name": "Off", "site_location": "", "account_name": "Off",
           "location": "A", "measured_by": "R", "witnessed_by": "", "notes": "",
           "items": [], "company_branch": "", "auth_signatory": "",
           "created_at": "2026-09-12 09:00", "created_by": "somebody-else",
           "grid_model": MS.GRID_MODEL_JOINT, "grid_columns": [], "grid_rows": []}
    rec.update(over)
    STORE.setdefault("boqs", {})[rec["boq_id"]] = {
        "id": rec["boq_id"], "ref": "SF/BOQ/26-27/0001", "rev_no": 0,
        "supersedes": "", "line_items": [], "project_name": "Off"}
    STORE.setdefault("measurements", {})[mid] = rec
    return rec


def _an_invoice(iid="off-ti", **over):
    rec = {"id": iid, "ref": "SF/TI/26-27/0009", "fy": "26-27", "date": "2026-09-12",
           "proforma_id": "", "proforma_ref": "", "quotation_id": "", "quotation_ref": "",
           "account_name": "Off", "contact_person": "", "to": "Off", "bill_gstin": "",
           "ship_same": "on", "line_items": [], "subtotal": 0.0, "tax_type": "cgst_sgst",
           "tax_info": {"CGST": 0.0, "SGST": 0.0, "total": 0.0, "cgst_rate": 9.0, "sgst_rate": 9.0},
           "grand_total": 0.0, "total_qty": 0.0, "place_of_supply": "Maharashtra",
           "pos_code": "27", "reverse_charge": False, "advance_received": 0.0,
           "net_payable": 0.0, "created_by": "somebody-else"}
    rec.update(over)
    STORE.setdefault("invoices", {})[iid] = rec
    return rec


def _a_purchase(pid="off-po", **over):
    rec = {"id": pid, "ref": "SF/PO/26-27/0009", "fy": "26-27", "date": "2026-09-12",
           "vendor_id": "", "vendor_name": "V", "vendor_gstin": "", "to": "V",
           "vendor_ref": "", "quotation_id": "", "quotation_ref": "",
           "line_items": [], "extra_lines": [], "subtotal": 0.0, "charges": [],
           "taxable_value": 0.0, "tax_type": "exempt", "tax_info": {"total": 0.0},
           "grand_total": 0.0, "total_qty": 0.0, "status": "Draft",
           "status_history": [], "notes": "", "created_by": "somebody-else"}
    rec.update(over)
    STORE.setdefault("purchases", {})[pid] = rec
    return rec


def _a_merged(mid="off-mi", **over):
    rec = {"id": mid, "tax_invoice_ref": "SF/MI/26-27/0009", "fy": "26-27",
           "date": "2026-09-12", "supply_ra_id": "x", "installation_ra_id": "y",
           "supply_ref": "", "installation_ref": "", "supply_ra_no": 1,
           "installation_ra_no": 2, "boq_id": "", "boq_ref": "", "project_name": "",
           "site_location": "", "account_name": "", "contact_person": "", "to": "",
           "bill_gstin": "", "claim_subtotal": 0.0, "deduction_total": 0.0,
           "net_payable": 0.0, "tax_amount": 0.0, "rounding_off": 0.0,
           "grand_total": 0.0, "status": "live", "cancelled_on": "",
           "cancel_reason": "", "notes": "", "created_by": "somebody-else"}
    rec.update(over)
    STORE.setdefault("merged_ras", {})[mid] = rec
    return rec


BUILDERS = {
    "charge":      lambda **o: _a_charge("off-ch", **o),
    "ra":          lambda **o: _a_bill("off-ra", **o),
    "merged_ra":   lambda **o: _a_merged("off-mi", **o),
    "invoice":     lambda **o: _an_invoice("off-ti", **o),
    "purchase":    lambda **o: _a_purchase("off-po", **o),
    "measurement": lambda **o: _a_measurement("off-ms", **o),
}


def _role_users():
    return {slug: _user(f"off-{slug}", slug) for slug in ROLE_SLUGS}


# ═══ 0. The switch, as shipped ═════════════════════════════════════════════

def test_the_switch_is_shipped_off_and_read_through_one_accessor():
    assert approval.LADDER_ON is False
    assert approval.ladder_on() is False
    assert auth.approvals_switched_off() is True
    assert auth.blueprint_off_reason("approval") == auth.OFF_APPROVALS
    assert auth.endpoint_off_reason("approval.approve_ra") == auth.OFF_APPROVALS
    # the other toggle is untouched by this one
    assert auth.blueprint_off_reason("product") == auth.OFF_HIDDEN
    assert auth.blueprint_off_reason("spec") == ""


def test_every_document_in_the_table_has_a_row_here():
    assert set(BUILDERS) == set(approval.DOCUMENTS)


def test_no_settings_control_exists_for_the_switch():
    """Code only: a toggle the client could reach would switch on deferred scope."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "settings.py").read_text(encoding="utf8")
    assert "LADDER_ON" not in src and "ladder_on" not in src and "approval" not in src.lower().replace("approval_migration", "")


def test_nothing_reads_the_constant_directly():
    """
    Every reader goes through `ladder_on()`; a reader that bound the constant
    at import would miss a flip. Read at AST level — comments and docstrings
    name the constant freely, code may not.
    """
    import ast
    import pathlib
    repo = pathlib.Path(__file__).resolve().parent.parent
    for path in sorted(repo.glob("*.py")) + sorted((repo / "tools").glob("*.py")):
        if path.name == "approval.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "LADDER_ON":
                raise AssertionError(f"{path.name}:{node.lineno} reads approval.LADDER_ON "
                                     f"directly instead of approval.ladder_on()")


# ═══ 1. Every approve/reject route is refused for everyone ═════════════════

@pytest.mark.parametrize("doc_key", sorted(approval.DOCUMENTS))
@pytest.mark.parametrize("verb", ["approve", "reject"])
@pytest.mark.parametrize("slug", ROLE_SLUGS)
def test_every_approval_route_is_refused_for_every_role_on_both_methods(
        client, doc_key, verb, slug):
    """
    Refused at the gate, before the permission is consulted — so the Owner,
    who holds every `*.approve`, is refused exactly as the Accountant, who
    holds none. Nothing is written: the record is byte-identical afterwards.
    """
    user = _role_users()[slug]
    _as(client, user)
    rec = BUILDERS[doc_key]()
    before = copy.deepcopy(rec)
    url = f"/approval/{verb}/{doc_key}/{rec['id']}"

    r = client.get(url)
    assert r.status_code == 403, f"{slug} GET {url} -> {r.status_code}"
    body = r.get_data(as_text=True)
    assert "Approvals are switched off" in body
    assert "approval.LADDER_ON" in body
    assert "roles and their permissions are unchanged" in body

    r = client.post(url, data={"reason": "no"})
    assert r.status_code == 403, f"{slug} POST {url} -> {r.status_code}"
    assert "Approvals are switched off" in r.get_data(as_text=True)

    assert rec == before, "an approval route wrote to the record while switched off"
    assert approval.status_of(rec) == approval.PENDING
    assert approval.approvals_of(rec) == []


@pytest.mark.parametrize("doc_key", sorted(approval.DOCUMENTS))
def test_a_stranger_gets_the_login_bounce_not_the_switched_off_page(anon_client, doc_key):
    for verb in ("approve", "reject"):
        r = anon_client.get(f"/approval/{verb}/{doc_key}/anything", follow_redirects=False)
        assert r.status_code in (302, 303)
        assert "/login" in r.headers.get("Location", "")
        assert "switched off" not in r.get_data(as_text=True)


def test_the_refusal_is_logged_with_its_own_reason(client):
    _a_bill("off-log")
    auth.REFUSAL_LOG.clear()
    client.get("/approval/approve/ra/off-log")
    assert auth.REFUSAL_LOG[0]["reason"] == auth.OFF_APPROVALS
    assert auth.REFUSAL_LOG[0]["endpoint"] == "approval.approve_ra"


@pytest.mark.parametrize("slug", ROLE_SLUGS)
def test_can_reach_mirrors_the_gate_for_every_role(client, slug):
    user = _role_users()[slug]
    for doc_key in approval.DOCUMENTS:
        for verb in ("approve", "reject"):
            assert not auth.can_reach(f"approval.{verb}_{doc_key}", user), (
                f"can_reach says {slug} may reach approval.{verb}_{doc_key} while off")


def test_can_approve_refuses_everything_by_name(client, cast):
    rec = _a_charge("off-guard")
    for who in cast.values():
        allowed, why = approval.can_approve("charge", rec, who)
        assert not allowed and why == approval.SWITCHED_OFF_NOTE
    # and nothing can reach either state: the only writers are the routes,
    # which are refused, and `record_approval()` is never reached
    assert approval.actions("charge", rec, cast["director"]) == ""


def test_the_view_refuses_on_its_own_even_if_the_gate_were_loosened(client, cast):
    """Defence in depth: `_do_approve()` and `_do_reject()` check the switch first."""
    rec = _a_charge("off-deep")
    with client.application.test_request_context("/approval/approve/charge/off-deep",
                                                 method="POST"):
        body, status = approval._do_approve("charge", "off-deep")
        assert status == 403 and "Approvals are switched off" in body
        body, status = approval._do_reject("charge", "off-deep")
        assert status == 403 and "Approvals are switched off" in body
    assert approval.approvals_of(rec) == []
    assert approval.status_of(rec) == approval.PENDING


# ═══ 2. No queue, tile, chip or band ═══════════════════════════════════════

def test_an_undecided_record_draws_no_chip_no_panel_no_marker(client):
    for doc_key, build in BUILDERS.items():
        rec = build()
        assert approval.cell(doc_key, rec) == "", doc_key
        assert approval.panel(doc_key, rec) == "", doc_key
    old = _a_charge("off-gf", created_by=None, pre_approval_system=True)
    assert approval.cell("charge", old) == "" and approval.panel("charge", old) == ""
    assert approval.raised_while_off_chip(old) == ""


def test_the_ra_register_and_view_carry_no_approval_furniture(client):
    _a_bill("off-reg", status="issued")
    listing = client.get("/ra/").get_data(as_text=True)
    assert "AWAITING APPROVAL" not in listing and "Approve</a>" not in listing
    view = client.get("/ra/view/off-reg").get_data(as_text=True)
    assert "AWAITING APPROVAL" not in view and ">APPROVAL</b>" not in view
    assert "Creator unknown" not in view


def test_the_dashboard_has_no_pending_approval_tile_and_counts_nothing_pending(client):
    _a_bill("off-tile", status="issued")
    assert dashboard._ra_awaits_approval(STORE["ra_bills"]["off-tile"]) is False
    assert dashboard._boq_ra()["ra_pending_count"] == 0
    html = client.get("/").get_data(as_text=True)
    assert "RAs pending approval" not in html
    assert "waiting on an approver" not in html


def test_the_measurement_card_counts_saved_sheets_not_approvals(client):
    _a_measurement("off-card-1")
    _a_measurement("off-card-2", approval_status=approval.REJECTED)
    m = dashboard._metrics()
    assert m["ms_total"] == 2 and m["ms_approved"] == 1
    html = client.get("/").get_data(as_text=True)
    assert "counting toward installation claims" in html
    assert "1 approved" not in html


# ═══ 3. Pending, grandfathered and raised-while-off records are not gated ═══

def test_a_pending_issued_bill_prints(client):
    _a_bill("off-print", status="issued")
    r = client.get("/ra/print/off-print")
    assert r.status_code == 200
    assert approval.PRINT_BLOCK_MARKER not in r.get_data(as_text=True)


def test_a_grandfathered_bill_still_prints(client):
    _a_bill("off-gf-print", status="issued", created_by=None, pre_approval_system=True)
    assert client.get("/ra/print/off-gf-print").status_code == 200


def test_a_bill_raised_while_off_prints(client):
    _a_bill("off-stamped", status="issued", **{approval.RAISED_WHILE_OFF_FIELD: True})
    assert client.get("/ra/print/off-stamped").status_code == 200


def test_a_pending_tax_invoice_and_purchase_order_emit_no_print_block(client):
    ti = _an_invoice("off-ti-view")
    po = _a_purchase("off-po-view", status="Issued")
    assert approval.print_block("invoice", ti) == ""
    assert approval.print_block("purchase", po) == ""
    assert approval.PRINT_BLOCK_MARKER not in client.get("/invoice/view/off-ti-view").get_data(as_text=True)
    assert approval.PRINT_BLOCK_MARKER not in client.get("/purchase/view/off-po-view").get_data(as_text=True)


def test_a_pending_merged_document_prints(client, pair):
    import merged_ra
    _chain, s_, i_ = pair
    doc, err = merged_ra.create(s_, i_)
    assert doc is not None, err
    assert approval.status_of(doc) == approval.PENDING
    assert doc[approval.RAISED_WHILE_OFF_FIELD] is True, "merged_ra.create() did not stamp"
    r = client.get(f"/merged/print/{doc['id']}")
    assert r.status_code == 200
    assert doc["tax_invoice_ref"] in r.get_data(as_text=True)


def test_a_pending_measurement_prints(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    ms = only_sheet()
    assert approval.status_of(ms) == approval.PENDING
    assert client.get(f"/measurement/print/{ms['id']}").status_code == 200


def test_a_pending_charges_attachment_downloads(client):
    """B8's gate reads `can_print()`, so it opens with the ladder."""
    import attachment
    before = set(STORE["charges"])
    r = client.post("/charge/new", data=charge_form(),
                    content_type="multipart/form-data")
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:300]
    charge = next(c for cid, c in STORE["charges"].items() if cid not in before)
    att = attachment.for_parent("charge", charge["id"])[0]
    assert approval.status_of(charge) == approval.PENDING
    r = client.get(f"/attachment/charge/download/{att['id']}")
    assert r.status_code == 200
    assert r.headers.get("Content-Disposition", "").startswith("attachment")


def test_edit_and_delete_follow_the_documents_own_rules(client, cast):
    """
    `can_modify()` allows an undecided record to anybody; what refuses is the
    module's own rule. 3A.06's draft-only RA edit still holds: an issued bill
    is refused by `ra.can_edit()`, a draft is not.
    """
    ch = _a_charge("off-edit", created_by=cast["director"]["id"])
    for who in cast.values():
        assert approval.can_modify("charge", ch, who) == (True, ""), who["username"]
    issued = _a_bill("off-issued", status="issued")
    draft = _a_bill("off-draft", status="draft")
    assert approval.can_modify("ra", issued, cast["sales"])[0] is True
    assert ra.can_edit(issued)[0] is False, "3A.06: an issued bill is not editable"
    assert ra.can_edit(draft)[0] is True
    r = client.get("/ra/edit/off-issued", follow_redirects=False)
    assert r.status_code in (302, 303) and "approved" not in _where(r).lower()


# ═══ 4. A decision already taken is never overturned ═══════════════════════

def test_an_approved_record_is_locked_and_prints_exactly_as_today(client, cast):
    ch = _a_charge("off-approved", approval_status=approval.APPROVED,
                   approvals=[{"role": "director", "role_name": "Director",
                               "user_id": "d", "user_name": "D", "at": "x"}])
    assert approval.can_print("charge", ch) == (True, "")
    allowed, why = approval.can_modify("charge", ch, cast["owner"])
    assert not allowed and "locked" in why
    assert approval.can_approve("charge", ch, cast["hr"])[0] is False
    # the decision stays on the screen
    assert "APPROVED" in approval.cell("charge", ch)
    assert "Approve</a>" not in approval.cell("charge", ch)
    assert "APPROVED" in approval.panel("charge", ch) and "Director" in approval.panel("charge", ch)


def test_a_rejected_record_refuses_to_print_and_returns_to_its_creator(client, cast):
    ch = _a_charge("off-rejected", created_by=cast["director"]["id"],
                   approval_status=approval.REJECTED, reject_reason="wrong")
    allowed, why = approval.can_print("charge", ch)
    assert not allowed and "rejected" in why
    assert approval.can_modify("charge", ch, cast["director"]) == (True, "")
    allowed, why = approval.can_modify("charge", ch, cast["hr"])
    assert not allowed and "did not raise it" in why
    assert "REJECTED" in approval.cell("charge", ch)
    issued = _a_bill("off-rej-print", status="issued", approval_status=approval.REJECTED)
    r = client.get("/ra/print/off-rej-print", follow_redirects=False)
    assert r.status_code in (302, 303) and "rejected" in _where(r)


def test_nothing_can_reach_approved_or_rejected_while_off(client, cast):
    rec = _a_charge("off-unreachable")
    for who in cast.values():
        for verb in ("approve", "reject"):
            _as(client, who)
            client.post(f"/approval/{verb}/charge/off-unreachable", data={"reason": "x"})
    assert approval.status_of(rec) == approval.PENDING
    assert "approval_status" not in rec and "approvals" not in rec


# ═══ 5. The DRAFT overprint and a CANCELLED bill print ═════════════════════

def test_a_draft_prints_stamped_DRAFT_and_a_cancelled_bill_prints(client):
    _a_bill("off-d", status="draft")
    html = client.get("/ra/print/off-d").get_data(as_text=True)
    assert '<div class="lc-mark lc-draft">DRAFT</div>' in html
    assert "This is a DRAFT and has not been issued" in html
    _a_bill("off-c", status="cancelled", cancelled_on="2026-09-01", cancel_reason="withdrawn")
    html = client.get("/ra/print/off-c").get_data(as_text=True)
    assert "CANCELLED" in html


# ═══ 6. /roles: every *.approve box disabled and frozen ════════════════════

APPROVE_PERMS = {spec["permission"] for spec in approval.DOCUMENTS.values()}


def test_the_frozen_set_is_exactly_the_approve_permissions():
    assert auth.switched_off_permissions() == APPROVE_PERMS
    assert auth.frozen_permissions() == APPROVE_PERMS | auth.hidden_permissions()
    for pid in APPROVE_PERMS:
        assert auth.frozen_reason(pid) == auth.OFF_APPROVALS


def _label_of(html: str, pid: str) -> str:
    at = html.index(f"<code>{pid}</code>")
    start = html.rindex("<label", 0, at)
    end = html.index("</label>", at)
    return html[start:end]


def test_the_roles_editor_draws_approve_grants_disabled_and_says_switched_off(client):
    auth.ensure_builtin_roles()
    html = client.get("/roles/edit/role-director").get_data(as_text=True)
    for pid in APPROVE_PERMS:
        block = _label_of(html, pid)
        assert "disabled" in block and 'name="permissions"' not in block, pid
        assert "switched off" in block and "module hidden" not in block, pid
    director = set(STORE["roles"]["role-director"]["permissions"])
    for pid in APPROVE_PERMS & director:
        assert "checked" in _label_of(html, pid), f"{pid} is held but drawn unticked"
    spec_block = _label_of(html, "spec.view")
    assert 'name="permissions"' in spec_block and "disabled" not in spec_block


def test_a_save_that_omits_the_approve_boxes_keeps_them(client):
    auth.ensure_builtin_roles()
    role = STORE["roles"]["role-director"]
    before = sorted(role["permissions"])
    visible = [p for p in before if p not in APPROVE_PERMS]
    r = client.post("/roles/edit/role-director", data={"permissions": visible})
    assert r.status_code in (302, 303)
    assert sorted(role["permissions"]) == before


def test_a_hand_made_post_can_neither_add_nor_remove_an_approve_grant(client):
    auth.ensure_builtin_roles()
    hr = STORE["roles"]["role-hr"]
    assert "ra.approve" not in hr["permissions"] and "charge.approve" in hr["permissions"]
    client.post("/roles/edit/role-hr", data={"permissions": list(hr["permissions"]) + ["ra.approve"]})
    assert "ra.approve" not in hr["permissions"]
    client.post("/roles/edit/role-hr", data={"permissions": [p for p in hr["permissions"] if p != "charge.approve"]})
    assert "charge.approve" in hr["permissions"]


def test_a_new_role_starts_with_no_approve_grant(client):
    auth.ensure_builtin_roles()
    r = client.post("/roles/create", data={"name": "Off probe",
                                           "permissions": ["spec.view", "ra.approve"]})
    assert r.status_code in (302, 303)
    made = next(x for x in STORE["roles"].values() if x["name"] == "Off probe")
    assert made["permissions"] == ["spec.view"]


def test_the_permissions_and_registry_rows_are_kept():
    for pid in APPROVE_PERMS:
        assert pid in auth.PERMISSIONS
    for doc_key in approval.DOCUMENTS:
        for verb in ("approve", "reject"):
            assert f"approval.{verb}_{doc_key}" in auth.ROUTE_PERMISSIONS
    assert APPROVE_PERMS <= set(auth.BUILTIN_ROLES["owner"][1])


def test_the_access_matrix_marks_the_approve_grants_switched_off():
    import pathlib
    text = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "ACCESS_MATRIX.md").read_text(encoding="utf8")
    for pid in APPROVE_PERMS:
        row = next(line for line in text.splitlines() if f"`{pid}` |" in line and "<br/>" in line)
        assert "switched off" in row and "⊗" in row, row
        assert "·" not in row, f"{pid}'s row still shows a live grant mark: {row}"
    assert "approval.LADDER_ON = False" in text


# ═══ 7. THE TRAP — the measurement cap still binds ═════════════════════════

def test_a_saved_sheet_feeds_the_ceiling_while_off(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    ms = only_sheet()
    assert approval.status_of(ms) == approval.PENDING
    assert MS.feeds_ceiling(ms)
    assert MS.approved_qty_by_line(seeded) == {li["line_id"]: 2.0}, (
        "a saved sheet is not the ceiling while the ladder is off — ra.py "
        "would read {} and fall back to the BOQ quantity")
    assert MS.has_approved_measurement(seeded)


def test_an_installation_claim_above_the_saved_sheet_is_refused(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    claim = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 4.0}]
    breaches = ra.overclaims(seeded, "installation", claim)
    assert breaches and breaches[0]["reason"] == "overmeasured", (
        "4 was claimed against 3 saved and passed — the cap does not bind while off")
    assert not ra.overclaims(seeded, "installation",
                             [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 3.0}])


def test_a_line_the_saved_sheet_did_not_measure_cannot_be_claimed(client, seeded):
    a, b = [x for x in priced(seeded) if x["total_qty"] >= 4][:2]
    raise_sheet(client, seeded, [(a["line_id"], 2)])
    breaches = ra.overclaims(seeded, "installation",
                             [{"line_id": b["line_id"], "item_no": b["item_no"], "qty": 1.0}])
    assert breaches and breaches[0]["reason"] == "not_measured"
    assert "no measurement behind it" in ra.overclaim_message(breaches[0])
    assert "approved" not in ra.overclaim_message(breaches[0])


def test_a_rejected_sheet_still_counts_for_nothing(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    only_sheet()["approval_status"] = approval.REJECTED
    assert MS.approved_qty_by_line(seeded) == {}
    assert not MS.has_approved_measurement(seeded)


def test_c1_is_satisfied_by_a_saved_sheet_and_still_refuses_with_none(client, seeded):
    r = client.get(f"/ra/create?boq={seeded}&leg=installation", follow_redirects=False)
    assert r.status_code in (302, 303), "C1 opened the installation form with no sheet"
    assert "Raise a measurement sheet" in _where(r)
    assert "approved" not in _where(r), "the refusal tells the operator to get an approval nobody can give"
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    r = client.get(f"/ra/create?boq={seeded}&leg=installation")
    assert r.status_code == 200 and "ra_json" in r.get_data(as_text=True)


def test_the_boq_page_offers_the_installation_claim_on_a_saved_sheet(client, seeded):
    from conftest import chain_ready
    chain_ready(seeded, legs=("supply",))
    html = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "leg=installation" not in html
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    html = client.get(f"/boq/view/{seeded}").get_data(as_text=True)
    assert "leg=installation" in html


def test_a_saved_sheet_a_claim_rests_on_cannot_be_deleted(client, seeded):
    from test_measurement import _installation_bill
    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    ms = only_sheet()
    assert MS.can_delete(ms) == (True, "")
    _installation_bill(seeded, [li])
    allowed, why = MS.can_delete(ms)
    assert not allowed and "cannot be deleted" in why
    r = client.post(f"/measurement/delete/{ms['id']}", follow_redirects=False)
    assert r.status_code in (302, 303) and ms["id"] in STORE["measurements"]


def test_the_grandfather_path_never_fires_for_a_project_with_sheets(client, seeded):
    """
    `ra.py`'s `{}`-means-grandfather branch keeps the BOQ ceiling. With a
    saved sheet on the chain it must NOT fire: a claim between the sheet's
    figure and the BOQ's is the tell.
    """
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    between = [{"line_id": li["line_id"], "item_no": li["item_no"],
                "qty": min(9.0, li["total_qty"] - 1)}]
    assert ra.overclaims(seeded, "installation", between), (
        "a claim above the sheet and below the BOQ passed: ra.py read the "
        "ceiling as {} and fell back to the schedule")


# ── the mutation proofs ─────────────────────────────────────────────────────

def test_MUTATION_the_cap_reads_accepted_and_not_a_literal_status(client, seeded, monkeypatch):
    """Replace `accepted()` with the pre-switch reading; the cap assertion fails."""
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    claim = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 4.0}]
    assert ra.overclaims(seeded, "installation", claim)
    monkeypatch.setattr(approval, "accepted", approval.is_approved)
    assert not ra.overclaims(seeded, "installation", claim), (
        "the mutation was not caught: the cap does not depend on accepted()")


def test_MUTATION_the_empty_path_would_fire_without_the_branch(client, seeded, monkeypatch):
    """With the branch removed the ceiling reads `{}` and ra.py falls back to the BOQ."""
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    monkeypatch.setattr(MS, "feeds_ceiling", approval.is_approved)
    assert MS.approved_qty_by_line(seeded) == {}
    between = [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 5.0}]
    assert not ra.overclaims(seeded, "installation", between), "the {} path did not fire under mutation"
    assert not MS.has_approved_measurement(seeded)


# ═══ 8. Every record created while OFF is stamped at create ════════════════

def test_stamp_creator_writes_the_mark_while_off_and_not_while_on(client):
    rec = {}
    approval.stamp_creator(rec, user={"id": "u1"})
    assert rec[approval.RAISED_WHILE_OFF_FIELD] is True and rec["created_by"] == "u1"
    assert approval.raised_while_off(rec)
    approval.LADDER_ON = True
    try:
        on = {}
        approval.stamp_creator(on, user={"id": "u1"})
        assert approval.RAISED_WHILE_OFF_FIELD not in on
        assert not approval.raised_while_off(on)
    finally:
        approval.LADDER_ON = False


def test_every_create_route_stamps_the_mark(client, seeded):
    """The real routes, not the helper: a charge, an RA bill, a measurement."""
    from conftest import chain_ready
    r = client.post("/charge/new", data=charge_form(), content_type="multipart/form-data")
    assert r.status_code in (302, 303)
    charge = list(STORE["charges"].values())[-1]
    assert charge[approval.RAISED_WHILE_OFF_FIELD] is True

    li = next(x for x in priced(seeded) if x["total_qty"] >= 4)
    raise_sheet(client, seeded, [(li["line_id"], 2)])
    assert only_sheet()[approval.RAISED_WHILE_OFF_FIELD] is True

    chain_ready(seeded, legs=("supply",))
    r = client.post(f"/ra/create?boq={seeded}&leg=supply", data={
        "date": "2026-09-12",
        "ra_json": json.dumps({"lines": [{"line_id": li["line_id"], "qty": "1",
                                          "rate": str(li["supply_rate"])}]})})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:300]
    bill = list(STORE["ra_bills"].values())[-1]
    assert bill[approval.RAISED_WHILE_OFF_FIELD] is True


def test_the_mark_is_never_inferred_from_absence(client):
    plain = _a_bill("off-plain", status="issued")
    assert not approval.raised_while_off(plain)
    assert approval.gated(plain) is False, "gated() reads the switch, not the mark"
    approval.LADDER_ON = True
    try:
        assert approval.gated(plain) is True, "a PENDING record with no mark is on the ladder once it returns"
        assert approval.raised_while_off(plain) is False
    finally:
        approval.LADDER_ON = False


def test_viewing_and_printing_writes_nothing_onto_a_pending_record(client):
    rec = _a_bill("off-untouched", status="issued")
    before = copy.deepcopy(rec)
    client.get("/ra/view/off-untouched")
    client.get("/ra/print/off-untouched")
    client.get("/ra/")
    client.get("/")
    assert rec == before, "stored approval data was rewritten by a read"
    assert approval.RAISED_WHILE_OFF_FIELD not in rec


def test_MUTATION_a_missing_stamp_would_gate_the_record_when_the_ladder_returns(client, monkeypatch):
    """Stop the stamp; a record raised now is gated the day the ladder returns."""
    def _no_stamp(record, user=approval._UNSET):
        record["created_by"] = "u1"
    monkeypatch.setattr(approval, "stamp_creator", _no_stamp)
    rec = {"id": "m"}
    approval.stamp_creator(rec)
    approval.LADDER_ON = True
    try:
        assert approval.gated(rec) is True, "the mutation was not caught"
        assert approval.can_print("ra", dict(rec, status="issued"))[0] is False
    finally:
        approval.LADDER_ON = False


# ═══ 9. When the switch goes back ON ═══════════════════════════════════════

@pytest.mark.usefixtures("ladder_on")
def test_ON_a_record_raised_while_off_is_never_gated_or_queued_and_shows_its_mark(client, cast):
    assert approval.ladder_on()
    bill = _a_bill("on-stamped", status="issued", **{approval.RAISED_WHILE_OFF_FIELD: True})
    assert approval.can_print("ra", bill) == (True, "")
    assert approval.can_modify("ra", bill, cast["sales"]) == (True, "")
    allowed, why = approval.can_approve("ra", bill, cast["director"])
    assert not allowed and "raised while approvals were switched off" in why
    assert approval.actions("ra", bill, cast["director"]) == ""
    assert dashboard._ra_awaits_approval(bill) is False
    cell = approval.cell("ra", bill)
    assert "RAISED WHILE APPROVALS WERE OFF" in cell and "AWAITING" not in cell
    assert "Raised while approvals were off" in approval.panel("ra", bill)
    assert client.get("/ra/print/on-stamped").status_code == 200
    view = client.get("/ra/view/on-stamped").get_data(as_text=True)
    assert "Raised while approvals were off" in view
    r = client.get("/approval/approve/ra/on-stamped", follow_redirects=False)
    assert r.status_code in (302, 303) and "raised while approvals were switched off" in _where(r)
    assert approval.accepted(bill), "a raised-while-off record stands as accepted"


@pytest.mark.usefixtures("ladder_on")
def test_ON_a_record_raised_while_on_is_gated(client, cast):
    bill = _a_bill("on-fresh", status="issued")
    approval.stamp_creator(bill, user=cast["sales"])
    assert approval.RAISED_WHILE_OFF_FIELD not in bill
    assert approval.can_print("ra", bill)[0] is False
    assert approval.can_approve("ra", bill, cast["director"])[0] is True
    assert "AWAITING APPROVAL" in approval.cell("ra", bill)
    assert dashboard._ra_awaits_approval(bill) is True
    assert not approval.accepted(bill)


@pytest.mark.usefixtures("ladder_on")
def test_ON_a_record_pending_before_the_switch_went_off_returns_to_pending(client, cast):
    """No mark, so it is back on the ladder the day the ladder returns — by design."""
    bill = _a_bill("on-old-pending", status="issued")
    assert approval.RAISED_WHILE_OFF_FIELD not in bill
    assert approval.can_print("ra", bill)[0] is False
    assert dashboard._ra_awaits_approval(bill) is True
    assert approval.can_approve("ra", bill, cast["director"])[0] is True


@pytest.mark.usefixtures("ladder_on")
def test_ON_a_sheet_raised_while_off_goes_on_feeding_the_ceiling(client, seeded):
    li = next(x for x in priced(seeded) if x["total_qty"] >= 10)
    approval.LADDER_ON = False
    try:
        raise_sheet(client, seeded, [(li["line_id"], 3)])
    finally:
        approval.LADDER_ON = True
    ms = only_sheet()
    assert approval.raised_while_off(ms) and approval.status_of(ms) == approval.PENDING
    assert MS.approved_qty_by_line(seeded) == {li["line_id"]: 3.0}
    assert ra.overclaims(seeded, "installation",
                         [{"line_id": li["line_id"], "item_no": li["item_no"], "qty": 4.0}])
    # and a sheet raised now, while ON, waits for its approval as before
    STORE["measurements"].clear()
    raise_sheet(client, seeded, [(li["line_id"], 3)])
    assert MS.approved_qty_by_line(seeded) == {}


@pytest.mark.usefixtures("ladder_on")
def test_ON_the_routes_are_reachable_again_and_the_roles_boxes_are_live(client, cast):
    assert auth.blueprint_off_reason("approval") == ""
    assert auth.switched_off_permissions() == set()
    _as(client, cast["director"])
    _a_charge("on-route", created_by=cast["sales"]["id"])
    assert client.get("/approval/approve/charge/on-route").status_code == 200
    _as(client, cast["owner"])
    html = client.get("/roles/edit/role-director").get_data(as_text=True)
    block = _label_of(html, "ra.approve")
    assert 'name="permissions"' in block and "disabled" not in block


# ═══ 10. The e2e driver skips the ladder and says so ═══════════════════════

def test_the_e2e_driver_recognises_the_switched_off_page(client):
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "e2e_chain", pathlib.Path(__file__).resolve().parent.parent / "tools" / "e2e_chain.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _a_bill("off-e2e")
    page = client.get("/approval/approve/ra/off-e2e").get_data(as_text=True)
    assert mod.ladder_switched_off(page)
    assert not mod.ladder_switched_off(client.get("/ra/").get_data(as_text=True))
    assert not mod.ladder_switched_off("")
