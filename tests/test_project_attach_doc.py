"""
ATTACH A LOOSE DOCUMENT TO A PROJECT — §0 **fifty-eighth** block, item 3.

The client's ask from the 28 October 2026 Yogesh meeting: a purchase order,
proforma, work order or charge that was **never raised from a BOQ** should be
filable under a project from the project's own page. There was no way at all
before this — those four forms carry a project picker at **create** and
nothing afterwards, and three of the four modules have no edit screen offering
one.

**The three assertions that matter most:**

- `test_A_DOCUMENT_THAT_FOLLOWS_A_BOQ_IS_REFUSED` and its partner for detach.
  `pnl.project_of()` (28 October 2026, `a6ab6c4`) is the **one** answer to
  *"which project is this document on"*, and it derives that answer from the
  BOQ. A hand tag that disagreed with its schedule would be a **second**
  answer: `project_of()` would go on reporting the BOQ's project while the
  record carried something else, and the page, the P&L and the untagged-cost
  line would print different truths. The refusal **says why** and points at
  the BOQ's own Attach / Detach.
- `test_the_leaf_imports_no_document_module`. The whole reason `projtag.py`
  exists rather than four edits: `purchase.py` and `proforma.py` are being
  edited on an unpushed office-PC line, and one definition of the write cannot
  drift the way four can.
- `test_every_attach_and_detach_is_on_the_trail`. Who, when, from, to —
  appended, never edited.

⚠ **A TAX INVOICE IS NOT ATTACHABLE** and that is tested too: it inherits
  through its proforma at read time and nothing is written on it.
"""

import pytest

import pnl as PNL
import projtag as PT
from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

_OWNED = ("projects", "purchases", "proformas", "invoices", "work_orders",
          "charges", "boqs")


@pytest.fixture()
def world(client):
    """Two projects and one BOQ filed under the first."""
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["projects"]["p1"] = {
        "id": "p1", "name": "Jamnagar", "norm_name": "jamnagar",
        "client": "IOCL", "notes": "", "site_address_id": "",
        "site_address": "", "created_at": "2026-10-01 09:00",
        "updated_at": "2026-10-01 09:00"}
    STORE["projects"]["p2"] = {
        "id": "p2", "name": "Tower B", "norm_name": "tower b",
        "client": "Prudent", "notes": "", "site_address_id": "",
        "site_address": "", "created_at": "2026-10-01 09:00",
        "updated_at": "2026-10-01 09:00"}
    STORE["boqs"]["b1"] = {
        "id": "b1", "ref": "SF/BOQ/26-27/0019", "rev_no": 0, "supersedes": "",
        "date": "2026-10-01", "subtotal": 100000.0, "project_id": "p1",
        "line_items": []}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


def _po(pid="", boq_id="", ref="SF/PO/26-27/0007", status="Issued"):
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": ref, "date": "2026-10-12", "status": status,
        "vendor_name": "Acme Pipes", "project_id": pid, "project_name": "",
        "boq_id": boq_id, "taxable_value": 50000.0, "grand_total": 59000.0,
        "subtotal": 50000.0, "charges": [], "items": [],
        "status_history": []}
    return STORE["purchases"]["po1"]


def _pi(pid="", boq_id="", ref="SF/PI/26-27/0003"):
    STORE["proformas"]["pi1"] = {
        "id": "pi1", "ref": ref, "date": "2026-10-10", "project_id": pid,
        "boq_id": boq_id, "account_name": "IOCL", "subtotal": 20000.0,
        "grand_total": 23600.0, "line_items": []}
    return STORE["proformas"]["pi1"]


def _wo(pid="", ref="SF/WO/26-27/0002"):
    STORE["work_orders"]["wo1"] = {
        "id": "wo1", "ref": ref, "date": "2026-10-11", "status": "issued",
        "project_id": pid, "project_name": "", "items": []}
    return STORE["work_orders"]["wo1"]


def _ch(pid="", person="Ramesh Patil"):
    STORE["charges"]["ch1"] = {
        "id": "ch1", "person": person, "head": "Travel",
        "description": "Site visit", "date": "2026-10-09",
        "created_at": "2026-10-09 10:00", "project_id": pid,
        "project_name": "", "taxable_amount": 1200.0, "gst_amount": 0.0}
    return STORE["charges"]["ch1"]


def _post(client, action, kind, doc_id, pid="p1"):
    return client.post(f"/projects/view/{pid}",
                       data={"action": action, "doc": f"{kind}:{doc_id}"},
                       follow_redirects=True)


def _page(client, pid="p1"):
    r = client.get(f"/projects/view/{pid}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


# =============================================================================
# THE REFUSAL — a document that follows a BOQ
# =============================================================================

def test_A_DOCUMENT_THAT_FOLLOWS_A_BOQ_IS_REFUSED(world):
    """
    THE ASSERTION THAT MATTERS MOST (1 of 3). It follows its schedule, and a
    hand tag would be a second answer to a question `pnl.project_of()` already
    answers. The refusal names the schedule and the way forward.
    """
    _po(boq_id="b1")
    html = _post(world, "attach_doc", "purchase", "po1", pid="p2").get_data(as_text=True)
    assert "was raised from schedule SF/BOQ/26-27/0019" in html
    assert "second answer to a question that has one" in html
    assert "Attach or detach the BOQ instead" in html
    # …and NOTHING was written.
    assert STORE["purchases"]["po1"]["project_id"] == ""
    assert PT.TRAIL_FIELD not in STORE["purchases"]["po1"]


def test_a_boq_derived_document_cannot_be_DETACHED_either(world):
    """There is no hand tag to remove, and the refusal says so rather than
    appearing to have done something."""
    _po(boq_id="b1")
    html = _post(world, "detach_doc", "purchase", "po1").get_data(as_text=True)
    assert "follows schedule SF/BOQ/26-27/0019" in html
    assert "no hand tag to remove" in html
    assert PT.TRAIL_FIELD not in STORE["purchases"]["po1"]


def test_a_boq_derived_document_is_not_even_OFFERED(world):
    _po(boq_id="b1")
    assert PT.candidates()["purchase"] == []
    assert PT.attached("p1")["purchase"] == [], (
        "it IS on p1 — through its BOQ — but detaching it is meaningless")


def test_a_DELETED_schedule_leaves_the_document_hand_taggable(world):
    """
    ⚠ The two functions must agree. `project_of()` falls through to the stored
    tag when `boq_id` no longer resolves, so such a record is reported
    untagged there and must be attachable here — otherwise a document could be
    refused by one and called untagged by the other.
    """
    _po(boq_id="b-deleted-long-ago")
    assert PT.derives_from_boq(STORE["purchases"]["po1"]) == ""
    assert PNL.project_of(STORE["purchases"]["po1"]) == ""
    assert [d for d, _r in PT.candidates()["purchase"]] == ["po1"]
    _post(world, "attach_doc", "purchase", "po1")
    assert STORE["purchases"]["po1"]["project_id"] == "p1"


def test_a_tax_invoice_is_not_an_attachable_kind(world):
    """It inherits through its proforma at read time and carries no tag of its
    own. Tagging one by hand is the same second answer one document along."""
    assert "invoice" not in PT.KINDS
    note, err = PT.attach("invoice", "ti1", "p1", "tester")
    assert note == "" and "not a kind of document that can be attached" in err


def test_a_tax_invoice_still_follows_its_proforma_on_the_page(world):
    """The inheritance is untouched by this pass — `project_of(ti, "invoice")`,
    and nothing is written on the TI."""
    _pi(pid="p1")
    STORE["invoices"]["ti1"] = {
        "id": "ti1", "ref": "SF/TI/26-27/0004", "date": "2026-10-20",
        "proforma_id": "pi1", "project_id": "", "subtotal": 20000.0,
        "grand_total": 23600.0, "account_name": "IOCL"}
    assert PNL.project_of(STORE["invoices"]["ti1"], "invoice") == "p1"
    assert STORE["invoices"]["ti1"]["project_id"] == "", "nothing stored on it"
    assert "SF/TI/26-27/0004" in _page(world)


# =============================================================================
# THE WRITE — all four kinds
# =============================================================================

@pytest.mark.parametrize("kind,maker,did,label", [
    ("purchase",  _po, "po1", "SF/PO/26-27/0007"),
    ("proforma",  _pi, "pi1", "SF/PI/26-27/0003"),
    ("workorder", _wo, "wo1", "SF/WO/26-27/0002"),
    ("charge",    _ch, "ch1", "Ramesh Patil"),
])
def test_each_kind_attaches_and_snapshots_the_project_name(world, kind, maker,
                                                           did, label):
    maker()
    html = _post(world, "attach_doc", kind, did).get_data(as_text=True)
    rec = PT.get(kind, did)
    assert rec["project_id"] == "p1", f"{kind} was not filed"
    assert rec["project_name"] == "Jamnagar", (
        "the name is snapshotted beside the id — charge.py's pattern, which "
        "purchase.py and workorder.py follow")
    assert f"filed under Jamnagar" in html
    assert label in _page(world), f"{kind} is not on the project page"


@pytest.mark.parametrize("kind,maker,did", [
    ("purchase",  _po, "po1"),
    ("proforma",  _pi, "pi1"),
    ("workorder", _wo, "wo1"),
    ("charge",    _ch, "ch1"),
])
def test_each_kind_detaches_and_clears_the_snapshot(world, kind, maker, did):
    maker(pid="p1")
    PT.get(kind, did)["project_name"] = "Jamnagar"
    _post(world, "detach_doc", kind, did)
    rec = PT.get(kind, did)
    assert rec["project_id"] == ""
    assert rec["project_name"] == ""


def test_a_document_on_ANOTHER_project_is_not_silently_detached(world):
    """DOMAIN.md §6's rule, and exactly what the BOQ detach branch already
    does: this page may not quietly rewrite a record belonging to somebody
    else's job."""
    _po(pid="p2")
    html = _post(world, "detach_doc", "purchase", "po1").get_data(as_text=True)
    assert "is not filed under this project" in html
    assert STORE["purchases"]["po1"]["project_id"] == "p2"


def test_attaching_what_is_already_here_is_refused_not_re_logged(world):
    _po(pid="p1")
    html = _post(world, "attach_doc", "purchase", "po1").get_data(as_text=True)
    assert "already filed under this project" in html
    assert PT.TRAIL_FIELD not in STORE["purchases"]["po1"]


def test_moving_between_projects_is_one_attach(world):
    _po(pid="p2")
    _post(world, "attach_doc", "purchase", "po1", pid="p1")
    rec = STORE["purchases"]["po1"]
    assert rec["project_id"] == "p1"
    entry = PT.trail_of(rec)[0]
    assert (entry["from"], entry["to"]) == ("p2", "p1")
    assert (entry["from_name"], entry["to_name"]) == ("Tower B", "Jamnagar")


# =============================================================================
# THE CANDIDATE LIST
# =============================================================================

def test_only_untagged_documents_are_offered(world):
    _po(pid="p2")
    assert PT.candidates()["purchase"] == []
    STORE["purchases"]["po1"]["project_id"] = ""
    assert [d for d, _r in PT.candidates()["purchase"]] == ["po1"]


def test_a_document_on_a_DELETED_project_is_offered_again(world):
    """
    `projectview.py`'s eligible-BOQ rule of 9 September 2026, one collection
    along: deleting a project leaves every record filed under it pointing at
    nothing, and without this it is offered by no project's picker and is
    unreachable from any screen.
    """
    _po(pid="p-gone")
    assert [d for d, _r in PT.candidates()["purchase"]] == ["po1"]


def test_a_po_in_DRAFT_is_still_offered(world):
    """Attaching is filing, not costing. `pnl.py` decides what a Draft order
    contributes (nothing), and that rule is not duplicated here."""
    _po(status="Draft")
    assert [d for d, _r in PT.candidates()["purchase"]] == ["po1"]


def test_the_panel_lists_each_kind_under_its_own_heading(world):
    _po(); _pi(); _wo(); _ch()
    html = _page(world)
    assert "<h2>Attach document</h2>" in html
    for group in ("Purchase Orders", "Proforma Invoices", "Work Orders",
                  "Charges"):
        assert f'<optgroup label="{group}">' in html


def test_the_value_carries_the_kind_so_an_id_cannot_cross_collections(world):
    """One select, `kind:id`. Four selects would be four chances to post a
    work order id against the purchases collection."""
    _wo()
    assert 'value="workorder:wo1"' in _page(world)
    note, err = PT.attach("purchase", "wo1", "p1", "tester")
    assert note == "" and "no longer exists" in err


def test_the_empty_states_say_what_is_true(world):
    html = _page(world)
    assert "Nothing is waiting to be attached" in html
    assert "Nothing on this project was filed by hand" in html


# =============================================================================
# THE TRAIL
# =============================================================================

def test_every_attach_and_detach_is_on_the_trail(world):
    """THE ASSERTION THAT MATTERS MOST (3 of 3). Who, when, from, to."""
    _po()
    _post(world, "attach_doc", "purchase", "po1")
    _post(world, "detach_doc", "purchase", "po1")
    trail = STORE["purchases"]["po1"][PT.TRAIL_FIELD]
    assert len(trail) == 2, "both moves are recorded"
    assert [e["action"] for e in trail] == [PT.ATTACH, PT.DETACH], (
        "appended in the order they happened, never edited")
    a, d = trail
    assert (a["from"], a["to"]) == ("", "p1")
    assert (d["from"], d["to"]) == ("p1", "")
    assert a["to_name"] == "Jamnagar", "the project NAME is snapshotted too"
    for e in trail:
        assert e["by"] == "Test Owner", f"who is missing: {e}"
        assert len(e["at"]) == 16, f"when is missing: {e}"


def test_the_trail_survives_the_project_being_renamed(world):
    """The names are snapshotted for the reason every snapshot in this app
    exists: an id alone would say nothing once the project is renamed."""
    _po()
    _post(world, "attach_doc", "purchase", "po1")
    STORE["projects"]["p1"]["name"] = "Jamnagar Phase 2"
    assert PT.trail_of(STORE["purchases"]["po1"])[0]["to_name"] == "Jamnagar"


def test_a_record_never_moved_by_hand_has_no_trail_key(world):
    """Absent means exactly that, and nothing is backfilled."""
    _po(pid="p1")
    assert PT.TRAIL_FIELD not in STORE["purchases"]["po1"]
    assert PT.trail_of(STORE["purchases"]["po1"]) == []


# =============================================================================
# THE GATE, AND THE LEAF
# =============================================================================

def test_the_post_needs_project_edit_not_project_view(world, monkeypatch):
    """The per-view guard the two BOQ branches already use. `project.view` is
    held by Sales, Purchase and Accounts; none holds `project.edit`."""
    _po()
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "project.edit" else real(p))
    r = world.post("/projects/view/p1",
                   data={"action": "attach_doc", "doc": "purchase:po1"})
    assert r.status_code == 403
    assert STORE["purchases"]["po1"]["project_id"] == ""


def test_the_panel_is_not_drawn_without_project_edit(world, monkeypatch):
    """A control that can only produce a refusal is not drawn — the owner's
    rule of 22 September 2026. Presentation, not the gate: the POST above
    refuses a typed form on its own."""
    _po()
    import auth
    real = auth.has_perm
    monkeypatch.setattr(auth, "has_perm",
                        lambda p: False if p == "project.edit" else real(p))
    assert "<h2>Attach document</h2>" not in _page(world)


def test_the_leaf_imports_no_document_module():
    """
    THE ASSERTION THAT MATTERS MOST (2 of 3), and the whole reason this module
    exists instead of four edits. `tests/test_import_directions.py` holds the
    full list; this is the short statement of it beside the behaviour.
    """
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "projtag.py")
    names = set()
    for node in ast.walk(ast.parse(src.read_text(encoding="utf8"))):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert names == {"datetime", "pipeline", "pnl", "store"}, (
        f"projtag.py imports {sorted(names)} — it must reach no document "
        f"module, above all not purchase.py or proforma.py, which are being "
        f"edited on an unpushed line")


def test_pnl_project_of_is_the_one_reader(world):
    """`projtag.project_of()` adds no second rule — it asks that function, so
    the attach list, the panels, the P&L and the untagged line cannot
    disagree."""
    _po(boq_id="b1")
    for kind, rec in (("purchase", STORE["purchases"]["po1"]),):
        assert PT.project_of(kind, rec) == PNL.project_of(rec) == "p1"
