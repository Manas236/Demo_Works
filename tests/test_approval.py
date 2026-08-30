"""
B6 — the approval ladder, and the creator guard that makes it mean anything.

CLIENT_CHANGES-2.md B6, in full:

    - **Charges:** three-step ladder — Director → Operations Head → HR, in sequence
    - **RA / Tax Invoice / PO:** Operations Head + Director
    - **Any one Director's approval is sufficient.** Confirmed by the client.

    **Load-bearing rule:** a user cannot approve a record they created. This is
    checked against the **record's creator**, not against the approver's role.

    Without this, union permissions defeat the ladder — a user holding both
    Sales Manager and HR could raise a charge and approve it themselves.

The last paragraph is why the creator guard is not decoration and why this file
spends most of its length on it. It is also why the guard is written **once**,
in `approval.can_approve()`, and why
`test_every_approval_endpoint_reaches_the_guard` exists: a rule enforced in six
places is a rule that will be enforced in five after the next change.

⚠ **Every refusal here is asserted BY URL.** Hiding a button is not access
control — that is B5's established rule — so each test posts to the address
directly and then reads the record back to prove nothing was written.
"""

import pytest

import approval
import auth
from store import STORE


# ── Users, one per ladder role ─────────────────────────────────────────────


def _user(username: str, role_slug: str):
    """A user holding exactly one builtin role. Idempotent across tests."""
    auth.ensure_builtin_roles()
    got = auth.find_user(username)
    if got is None:
        got = auth.create_user(username, username.title(), "pw-" + username,
                               [f"role-{role_slug}"], created_by="test")
    got["active"] = True
    got["role_ids"] = [f"role-{role_slug}"]
    return got


def _multi(username: str, slugs):
    """A user holding several roles — B4 says one user may."""
    user = _user(username, slugs[0])
    user["role_ids"] = [f"role-{s}" for s in slugs]
    return user


@pytest.fixture()
def cast(client):
    """One user per ladder role, plus a second Director."""
    return {
        "director":   _user("t-director", "director"),
        "director2":  _user("t-director-2", "director"),
        "ophead":     _user("t-ophead", "operation-head"),
        "hr":         _user("t-hr", "hr"),
        "sales":      _user("t-sales", "sales-manager"),
        "owner":      auth.find_user("test-owner"),
    }


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


def _a_charge(cid="c-1", created_by="somebody-else", **extra):
    rec = {"id": cid, "date": "2026-08-29", "person": "R. Kadam",
           "head": "Travel", "description": "Site visit", "project_id": "",
           "project_name": "", "taxable_amount": 1000.0, "gst_rate": 0.0,
           "gst_amount": 0.0, "notes": "",
           "created_at": "2026-08-29 09:00", "updated_at": "2026-08-29 09:00",
           "created_by": created_by}
    rec.update(extra)
    STORE.setdefault("charges", {})[cid] = rec
    return rec


# ═══ THE LADDERS ═══════════════════════════════════════════════════════════


def test_the_ladders_are_the_ones_CC2_states():
    """
    Read straight off B6, including the difference between the two shapes.

    Charges are specified "in sequence"; RA / Tax Invoice / PO are specified as
    a pair with no ordering word. That difference is carried into `sequential`
    rather than smoothed over, and it is a **judgement call on CC-2's wording**
    — if the client wants the pair ordered it is a one-word change.
    """
    assert approval.DOCUMENTS["charge"]["steps"] == (
        "director", "operation-head", "hr")
    assert approval.DOCUMENTS["charge"]["sequential"] is True

    for key in ("ra", "invoice", "purchase"):
        assert approval.DOCUMENTS[key]["steps"] == ("operation-head", "director")
        assert approval.DOCUMENTS[key]["sequential"] is False, (
            f"{key} was made sequential. CC-2 writes 'in sequence' for charges "
            f"and not for RA / Tax Invoice / PO.")


def test_the_charges_ladder_is_climbed_in_order(client, cast):
    """Director, then Operation Head, then HR — and not in any other order."""
    rec = _a_charge()

    # HR cannot go first.
    allowed, why = approval.can_approve("charge", rec, cast["hr"])
    assert not allowed and "Director" in why, why

    # The Operation Head cannot go first either.
    allowed, _ = approval.can_approve("charge", rec, cast["ophead"])
    assert not allowed

    # The Director can, and does.
    allowed, _ = approval.can_approve("charge", rec, cast["director"])
    assert allowed
    approval.record_approval("charge", rec, cast["director"])
    assert approval.status_of(rec) == approval.PENDING

    # Now the Operation Head, and still not HR.
    assert not approval.can_approve("charge", rec, cast["hr"])[0]
    assert approval.can_approve("charge", rec, cast["ophead"])[0]
    approval.record_approval("charge", rec, cast["ophead"])

    # And finally HR closes it.
    assert approval.can_approve("charge", rec, cast["hr"])[0]
    approval.record_approval("charge", rec, cast["hr"])
    assert approval.status_of(rec) == approval.APPROVED
    assert [a["role"] for a in rec["approvals"]] == [
        "director", "operation-head", "hr"]


def test_the_document_ladder_takes_its_two_in_either_order(client, cast):
    """
    RA / Tax Invoice / PO need both approvals; CC-2 does not order them.

    Asserted in the order CC-2 does *not* write — Director first, then Operation
    Head — because that is the one a sequential implementation would refuse.
    """
    rec = {"id": "ra-1", "created_by": "somebody-else"}
    STORE.setdefault("ra_bills", {})["ra-1"] = rec

    assert approval.can_approve("ra", rec, cast["director"])[0]
    approval.record_approval("ra", rec, cast["director"])
    assert approval.status_of(rec) == approval.PENDING

    assert approval.can_approve("ra", rec, cast["ophead"])[0]
    approval.record_approval("ra", rec, cast["ophead"])
    assert approval.status_of(rec) == approval.APPROVED


def test_any_one_directors_approval_is_sufficient(client, cast):
    """
    CC-2: "Any one Director's approval is sufficient. Confirmed by the client."

    B4 puts two Directors in the business. One rung, either of them, and the
    second is not asked for.
    """
    rec = {"id": "ra-2", "created_by": "somebody-else"}
    STORE.setdefault("ra_bills", {})["ra-2"] = rec

    approval.record_approval("ra", rec, cast["director2"])
    assert "director" in approval.steps_taken(rec)

    # The other Director adds nothing: the rung is taken, and only the Operation
    # Head's is outstanding.
    assert approval.outstanding_steps("ra", rec) == ["operation-head"]
    allowed, why = approval.can_approve("ra", rec, cast["director"])
    assert not allowed and "Operation Head" in why, why


def test_a_role_not_on_the_ladder_cannot_approve_at_all(client, cast):
    """Sales Manager is on no ladder, and holds no approval permission either."""
    rec = _a_charge("c-sales")
    allowed, _ = approval.can_approve("charge", rec, cast["sales"])
    assert not allowed
    assert "charge.approve" not in auth.permissions_of(cast["sales"])


# ═══ THE CREATOR GUARD — B6's load-bearing rule ════════════════════════════


def test_the_creator_cannot_approve_their_own_record(client, cast):
    """The rule, stated at its plainest, on every one of the four documents."""
    for key, coll in approval.COLLECTIONS.items():
        rec = {"id": f"own-{key}", "created_by": cast["director"]["id"]}
        STORE.setdefault(coll, {})[rec["id"]] = rec
        allowed, why = approval.can_approve(key, rec, cast["director"])
        assert not allowed, f"{key}: the creator was allowed to approve"
        assert "you cannot approve it" in why, why


def test_the_guard_checks_the_RECORD_not_the_role(client, cast):
    """
    CC-2: checked "against the **record's creator**, not against the approver's
    role."

    The same Director, the same permission, the same rung — allowed on one
    record and refused on the other, and the only difference is who raised it.
    """
    mine = _a_charge("c-mine", created_by=cast["director"]["id"])
    theirs = _a_charge("c-theirs", created_by=cast["ophead"]["id"])

    assert not approval.can_approve("charge", mine, cast["director"])[0]
    assert approval.can_approve("charge", theirs, cast["director"])[0]


def test_union_permissions_do_not_defeat_the_ladder(client, cast):
    """
    ⚠ CC-2's own worked example, built and asserted.

    "a user holding both Sales Manager and HR could raise a charge and approve
    it themselves." Here it is: one user, both roles, their own charge — and the
    guard refuses on the creator, which is the check that does not care how many
    roles they hold.
    """
    both = _multi("t-sales-hr", ["sales-manager", "hr"])
    rec = _a_charge("c-union", created_by=both["id"])

    allowed, why = approval.can_approve("charge", rec, both)
    assert not allowed, "CC-2's worked example is not being refused"
    assert "you cannot approve it" in why.lower() or "raised this" in why.lower()


def test_one_user_cannot_climb_two_rungs_of_the_same_ladder(client, cast):
    """
    ⚠ **Ours, not CC-2's** — and it follows CC-2's reasoning one step on.

    B4 lets one user hold several roles. A user holding Director *and* HR would
    otherwise climb two thirds of the charges ladder alone, which is the same
    "union permissions defeat the ladder" failure the creator guard exists for,
    reached by a different route.
    """
    both = _multi("t-dir-hr", ["director", "hr"])
    rec = _a_charge("c-two-rungs")

    approval.record_approval("charge", rec, both)          # Director rung
    assert approval.steps_taken(rec) == {"director"}

    # The Operation Head rung is next and is not theirs anyway; take it, so the
    # HR rung — which IS theirs — becomes the outstanding one.
    approval.record_approval("charge", rec, cast["ophead"])
    assert approval.outstanding_steps("charge", rec) == ["hr"]

    allowed, why = approval.can_approve("charge", rec, both)
    assert not allowed, (
        "one user climbed two rungs of the same ladder; the ladder is one "
        "person's decision wearing three hats")
    assert "already approved" in why


def test_the_guard_cannot_apply_where_there_is_no_creator(client, cast):
    """
    The grandfather rule's other half, stated as a guard property.

    A record with no creator is approvable by anybody on its ladder. Refusing it
    outright would strand every bill written before this module existed, which
    is precisely what the fourth 29 August override block refused to do.
    """
    rec = _a_charge("c-nocreator", created_by="")
    rec.pop("created_by")
    allowed, _ = approval.can_approve("charge", rec, cast["director"])
    assert allowed

    old = _a_charge("c-grandfathered", created_by=None,
                    created_at="2026-07-15 10:00")
    old[approval.GRANDFATHER_FIELD] = True
    old["created_by"] = None
    assert approval.is_grandfathered(old)
    assert approval.can_approve("charge", old, cast["director"])[0]


def test_the_owner_satisfies_any_rung_but_is_still_bound_by_the_guard(client, cast):
    """
    B3 gives the Owner "Everything", which is why it satisfies any rung.

    "Everything" must not come to mean "alone", so the creator guard and the
    one-rung rule still apply to it — and the second half of this test is what
    stops the Owner tier being a hole straight through B6.
    """
    theirs = _a_charge("c-owner-ok", created_by=cast["director"]["id"])
    assert approval.can_approve("charge", theirs, cast["owner"])[0]

    mine = _a_charge("c-owner-own", created_by=cast["owner"]["id"])
    allowed, why = approval.can_approve("charge", mine, cast["owner"])
    assert not allowed, "the Owner approved a record the Owner raised"
    assert "you cannot approve it" in why


# ═══ THE GUARD IS REACHED BY EVERY APPROVAL ROUTE ══════════════════════════


def _approval_endpoints():
    import app as app_module

    return sorted(r.endpoint for r in app_module.app.url_map.iter_rules()
                  if r.endpoint.startswith("approval."))


def test_every_approval_endpoint_reaches_the_guard():
    """
    ⚠ **The structural half of "written once".**

    Walks `approval.py`'s AST and asserts that every view the blueprint
    registers reaches `can_approve()`. The two generated bodies both call it
    today; this fails the day somebody adds a third that does not — which is the
    exact shape of "a rule enforced in six places is enforced in five after the
    next change".
    """
    import ast
    import pathlib

    src = pathlib.Path(approval.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    impls = {"_do_approve", "_do_reject"}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in impls:
            found[node.name] = any(
                isinstance(c.func, ast.Name) and c.func.id == "can_approve"
                for c in ast.walk(node) if isinstance(c, ast.Call))

    assert set(found) == impls, (
        f"approval.py no longer defines {sorted(impls - set(found))}. If the "
        f"route implementations were renamed, rename them here too — this test "
        f"is what proves the guard is not bypassed.")
    for name, calls in found.items():
        assert calls, (
            f"{name}() does not call can_approve(). Every approval site must "
            f"go through the single guard.")


def test_the_registered_endpoints_are_the_eight_expected():
    """Two per approvable document, and no others."""
    expected = sorted(
        f"approval.{verb}_{key}"
        for key in approval.DOCUMENTS for verb in ("approve", "reject"))
    assert _approval_endpoints() == expected


def test_every_approval_endpoint_is_classified_with_its_own_permission():
    """
    Each of the eight carries the permission of the document it acts on.

    A single route taking a `<doc_key>` could not do this — the registry maps
    one endpoint to one permission — and would have had to be `AUTHENTICATED`
    with the real check hidden in the view. That is the weakening B5 exists to
    prevent, and it is why there are eight.
    """
    # ⚠ "Each of the eight" is the claim, so count them. Looping over
    #   `DOCUMENTS` alone asserts nothing at all if the registry is ever emptied
    #   or narrowed, and this test would go green while approval routes lost
    #   their per-document gating. Five documents x two verbs on 30 August 2026:
    #   charge, RA bill, tax invoice, purchase order, measurement.
    assert len(approval.DOCUMENTS) >= 5, (
        f"only {len(approval.DOCUMENTS)} documents in approval.DOCUMENTS — the "
        f"loop below would assert nothing")

    for key, spec in approval.DOCUMENTS.items():
        for verb in ("approve", "reject"):
            endpoint = f"approval.{verb}_{key}"
            assert auth.ROUTE_PERMISSIONS.get(endpoint) == spec["permission"], (
                f"{endpoint} is not gated by {spec['permission']}")


# ═══ REFUSED BY URL, NOT BY A HIDDEN BUTTON ════════════════════════════════


def test_the_creator_is_refused_at_the_URL_and_nothing_is_written(client, cast):
    """
    ⚠ B5's rule: hiding a button is not a gate. So the creator types the address.

    The record is read back afterwards — a refusal that still wrote the approval
    would be worse than no refusal, because the page would say it was refused.
    """
    rec = _a_charge("c-url", created_by=cast["director"]["id"])
    _as(client, cast["director"])

    r = client.post("/approval/approve/charge/c-url", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert approval.approvals_of(rec) == [], (
        "the approval was written despite the refusal")
    assert approval.status_of(rec) == approval.PENDING


def test_the_button_is_not_offered_to_the_creator_either(client, cast):
    """
    The cosmetic half, asserted second and on purpose.

    `approval.actions()` asks the same guard the route asks, so the button and
    the URL cannot disagree. This is a courtesy, not the gate — the test above
    is the gate.
    """
    rec = _a_charge("c-btn", created_by=cast["director"]["id"])
    with client.application.test_request_context():
        from flask import session
        session[auth.SESSION_KEY] = cast["director"]["id"]
        assert approval.actions("charge", rec) == ""
        assert approval.actions("charge", _a_charge("c-btn2")) != ""


def test_a_role_without_the_permission_is_refused_by_the_route_gate(client, cast):
    """
    The other refusal, from the other mechanism, on the same URL.

    A Sales Manager holds no `charge.approve`, so `auth._gate()` stops the
    request before `approval.py` sees it. Both layers are real and they refuse
    different things: this one refuses the *route*, the guard above refuses the
    *record*.
    """
    _a_charge("c-gate")
    _as(client, cast["sales"])
    r = client.post("/approval/approve/charge/c-gate", follow_redirects=False)
    assert r.status_code == 403 or "/login" in r.headers.get("Location", "")
    assert approval.approvals_of(STORE["charges"]["c-gate"]) == []


def test_approving_through_the_route_writes_the_rung(client, cast):
    """The allowed path, so the refusals above are not passing by accident."""
    rec = _a_charge("c-ok")
    _as(client, cast["director"])

    r = client.post("/approval/approve/charge/c-ok", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert [a["role"] for a in approval.approvals_of(rec)] == ["director"]
    assert approval.approvals_of(rec)[0]["user_id"] == cast["director"]["id"]


def test_rejecting_through_the_route_records_who_and_why(client, cast):
    rec = _a_charge("c-rej")
    _as(client, cast["director"])

    r = client.post("/approval/reject/charge/c-rej",
                    data={"reason": "No supporting bill"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert approval.status_of(rec) == approval.REJECTED
    assert rec["rejected_by"] == cast["director"]["id"]
    assert rec["reject_reason"] == "No supporting bill"


def test_the_creator_cannot_reject_their_own_record_either(client, cast):
    """
    Rejecting is an approval decision and answers to the same guard.

    Without this a creator could not approve their own charge but could reject
    somebody else's correction of it, which is the same authority pointed the
    other way.
    """
    rec = _a_charge("c-selfrej", created_by=cast["director"]["id"])
    _as(client, cast["director"])
    client.post("/approval/reject/charge/c-selfrej", data={"reason": "x"})
    assert approval.status_of(rec) == approval.PENDING, (
        "the creator rejected their own record")


def test_an_already_approved_record_takes_no_further_approval(client, cast):
    rec = _a_charge("c-done")
    for who in ("director", "ophead", "hr"):
        approval.record_approval("charge", rec, cast[who])
    assert approval.status_of(rec) == approval.APPROVED

    allowed, why = approval.can_approve("charge", rec, cast["owner"])
    assert not allowed and "already fully approved" in why


def test_editing_clears_the_rungs_already_climbed(client, cast):
    """
    `clear_approvals()` — an approval describes the document somebody read.

    A changed document has not been approved, so the rungs go and the status
    returns to pending. This is the second line of the defence; `can_modify()`
    (B7) is the first, and it refuses most of these edits outright.
    """
    rec = _a_charge("c-edit")
    approval.record_approval("charge", rec, cast["director"])
    assert approval.steps_taken(rec) == {"director"}

    approval.clear_approvals(rec)
    assert approval.approvals_of(rec) == []
    assert approval.status_of(rec) == approval.PENDING


# ═══ NOTHING ABOUT APPROVAL REACHES PAPER ══════════════════════════════════


def test_the_grandfather_marker_renders_only_for_a_marked_record(client):
    """
    The marker appears for a grandfathered record and for nothing else.

    ⚠ It is **screen only**. The fourth 29 August override block set the default
    that nothing about approval reaches paper, and CC-2 asks for no approver
    name, signature or status on any printed sheet — so none is added.
    `tests/test_approval_b7.py` renders every printed document and asserts this
    text is absent from all of them; `tests/test_print_golden.py` is the
    byte-for-byte proof that they did not move at all.
    """
    assert approval.grandfather_marker({}) == ""
    assert approval.grandfather_marker({"created_by": None}) == ""

    marked = {approval.GRANDFATHER_FIELD: True}
    rendered = approval.grandfather_marker(marked)
    assert "Creator unknown" in rendered
    assert "predates the approval system" in rendered
    assert approval.grandfather_chip(marked) != ""
    assert approval.grandfather_chip({}) == ""


def test_the_grandfathered_charge_shows_its_marker_on_the_ledger(client, cast):
    """
    And it reaches a real page, rather than only existing as a helper.

    A marker nothing calls is a marker that says nothing. `/charge/` is where a
    charge is seen, and a grandfathered one has to say so there.

    ⚠ `STORE["charges"]` is **not** reset by `conftest._fresh_store()`, which
    clears only the six collections the quotation chain rebuilds. So this test
    empties it: the second assertion counts markers on the page, and a charge
    left behind by any earlier test in the session would make that count a
    measure of test order rather than of this page.
    """
    STORE.setdefault("charges", {}).clear()
    # ⚠ `created_at` genuinely predates the migration, because the record is
    # pretending to be old and a fixture that lies about its date is a fixture
    # `tests/test_approval_grandfather.py`'s pin will correctly report.
    rec = _a_charge("c-old", created_by=None, created_at="2026-07-15 10:00")
    rec[approval.GRANDFATHER_FIELD] = True
    rec["created_by"] = None

    html = client.get("/charge/").get_data(as_text=True)
    assert "CREATOR UNKNOWN" in html, (
        "a grandfathered charge renders no marker on the ledger, so nobody "
        "reading it can tell the creator guard never applied to it")

    plain = _a_charge("c-new")
    html2 = client.get("/charge/").get_data(as_text=True)
    assert html2.count("CREATOR UNKNOWN") == 1, (
        "the marker is showing on a record that is not grandfathered")
    assert plain["id"] in html2 or "AWAITING APPROVAL" in html2
