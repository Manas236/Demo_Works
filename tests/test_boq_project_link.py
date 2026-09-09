"""
A BOQ can be filed under a project THROUGH THE SCREEN — ABOUT.md §7 gap 33.

The defect this file exists to make impossible was two halves of one link that
never met. `boq.create_boq()` read `?project_id=` into its prefill on GET, and
its POST branch read `(form.get("project_id") or "").strip()` — but **the
rendered form contained no control of that name**, so the value posted was
always absent and every BOQ raised through the UI was stored with
`project_id: ""`.

    THE ASSERTION THAT MATTERS MOST is
    `test_the_create_form_renders_a_project_control`. Everything else here
    checks that the link behaves once it can be made; that one checks the
    control the whole defect consisted of missing is actually on the page.

**Why this is a defect and not a feature.** MG/SF/2026-02 §3 lists **F.04 —
"Project grouping — BOQs grouped under a project"** among the five items stated
to the client as built and handed over at no charge. The linkage on this repo's
own database was written by `tools/backfill_projects.py`; on a client box, which
starts empty, that tool never runs. So the sold behaviour was unreachable.
CLIENT_CHANGES.md §0's block of 9 September 2026 is the authority.

Scope note: `revision_chain()` and the whole-chain attach rule are untouched —
both were designed and correct. What is new is the control that feeds the link,
and the **detach** path that is the only way to correct a wrong one, there being
no `/boq/edit` route in this application.
"""

import json

import pytest

from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def clean():
    STORE["boqs"].clear()
    STORE["projects"].clear()
    yield
    STORE["boqs"].clear()
    STORE["projects"].clear()


def _mkproject(pid, name):
    STORE["projects"][pid] = {
        "id": pid, "name": name, "norm_name": name.lower().strip(),
        "client": "Prudent Teqtis Pvt Ltd", "notes": "",
        "site_address_id": "", "site_address": "Bangalore, Karnataka",
        "created_at": "2026-09-09T00:00:00", "updated_at": "2026-09-09T00:00:00",
    }
    return pid


def _form(rev_no="0", supersedes="", project_id=None,
          project="Sify Bangalore", account="Prudent Teqtis Pvt Ltd", **over):
    """A minimal but complete POST body for /boq/create.

    Shaped after `tests/test_boq_revisions.py::_form` deliberately — the same
    schedule, so a failure here is about the project link and nothing else.
    """
    rows = [
        {"line_id": "aaaaaaaaaaaa", "item_no": "1", "parent_item_no": "",
         "section": "A", "is_header": False, "description": "Line 1",
         "remark": "", "unit": "Mtrs", "area_qty": {}, "total_qty": "100",
         "supply_base_rate": "100", "supply_escalation_pct": "0",
         "supply_rate": "100", "supply_hsn": "73063090", "supply_gst_rate": "18",
         "install_base_rate": "50", "install_escalation_pct": "0",
         "install_rate": "50", "install_sac": "995462", "install_gst_rate": "18"}]
    data = {
        "date": "2026-08-12", "rev_no": rev_no, "supersedes": supersedes,
        "project_name": project, "account_name": account,
        "site_location": "Bangalore", "rate_basis_label": "Mohali Rates",
        "boq_json": json.dumps({
            "sections": [{"code": "A", "title": "Sprinkler", "areas": []}],
            "lines": rows}),
    }
    if project_id is not None:
        data["project_id"] = project_id
    data.update(over)
    return data


def _only_boq():
    """The single BOQ the store holds — the one the POST under test made."""
    assert len(STORE["boqs"]) == 1, f"expected 1 BOQ, got {len(STORE['boqs'])}"
    return next(iter(STORE["boqs"].values()))


def _mkchain(pid=""):
    """A two-link revision chain, both records carrying `pid`."""
    for bid, rev, sup in (("rev0", 0, ""), ("rev1", 1, "rev0")):
        STORE["boqs"][bid] = {
            "id": bid, "ref": f"SF/BOQ/26-27/000{rev + 1}", "fy": "26-27",
            "date": "2026-08-12", "rev_no": rev, "supersedes": sup,
            "project_id": pid, "project_name": "Sify Bangalore",
            "site_location": "Bangalore",
            "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "",
            "to": "", "bill_gstin": "", "ship_same": True,
            "rate_basis_label": "Mohali Rates",
            "sections": [{"code": "A", "title": "Sprinkler", "areas": []}],
            "line_items": [], "supply_subtotal": 0.0,
            "install_subtotal": 0.0, "subtotal": 0.0,
            "payment_terms": "", "delivery_terms": "", "notes": "",
            "company_branch": "", "auth_signatory": "",
        }
    return "rev0", "rev1"


# ═══ 1. A1 — the control that was missing ══════════════════════════════════

def test_the_create_form_renders_a_project_control(client, clean):
    """
    **The assertion this whole commit is for.**

    The route read `project_id` on both GET and POST and the form rendered no
    control of that name, so the field could not be posted by a browser at all.
    A `name="project_id"` on the create form is the entire difference between a
    link that can be made and one that cannot.
    """
    _mkproject("p1", "Sify Bangalore")
    html = client.get("/boq/create").get_data(as_text=True)
    assert 'name="project_id"' in html, \
        "the create form renders no project_id control — gap 33, exactly"


def test_the_control_lists_the_projects_that_exist(client, clean):
    _mkproject("p1", "Sify Bangalore")
    _mkproject("p2", "Magarpatta Tower B")
    html = client.get("/boq/create").get_data(as_text=True)
    assert 'value="p1"' in html and "Sify Bangalore" in html
    assert 'value="p2"' in html and "Magarpatta Tower B" in html


def test_the_control_offers_no_project_as_a_real_choice(client, clean):
    """
    Optional, not compulsory. A BOQ may legitimately precede its project — a
    schedule is often priced before the job is opened — so "none" is an
    offered answer rather than an omission.
    """
    _mkproject("p1", "Sify Bangalore")
    html = client.get("/boq/create").get_data(as_text=True)
    assert 'value=""' in html
    assert "not filed under a project" in html


def test_a_project_reached_from_its_own_page_is_preselected(client, clean):
    """
    `/projects/view/<id>` links here as `?project_id=<id>`. The route has always
    put that in its prefill; with no control on the form it went nowhere.
    """
    _mkproject("p1", "Sify Bangalore")
    _mkproject("p2", "Magarpatta Tower B")
    html = client.get("/boq/create?project_id=p2").get_data(as_text=True)
    assert '<option value="p2" selected>' in html, \
        "the ?project_id= a project page links with is not preselected"
    assert '<option value="p1" selected>' not in html


def test_posting_a_project_files_the_boq_under_it(client, clean):
    """The link, end to end, through the screen and nothing else."""
    _mkproject("p1", "Sify Bangalore")
    r = client.post("/boq/create", data=_form(project_id="p1"))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert _only_boq()["project_id"] == "p1"


def test_posting_no_project_stores_an_unattached_boq(client, clean):
    """
    The optional half. An unattached BOQ is a valid record whose claims roll up
    under *Unassigned*; it is not an error and is not refused.
    """
    _mkproject("p1", "Sify Bangalore")
    r = client.post("/boq/create", data=_form(project_id=""))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert _only_boq()["project_id"] == ""


def test_a_rejected_post_keeps_the_project_the_user_chose(client, clean):
    """
    A form that loses the project on an unrelated validation failure teaches
    the operator to distrust it. The date is what fails here.
    """
    _mkproject("p1", "Sify Bangalore")
    r = client.post("/boq/create", data=_form(project_id="p1", date=""))
    assert r.status_code == 200
    assert '<option value="p1" selected>' in r.get_data(as_text=True)


# ═══ 2. A3 — revision inheritance, verified rather than assumed ════════════

def test_a_revision_inherits_its_predecessors_project(client, clean):
    """
    Already true before this commit — `create_boq()` reads
    `prev.get("project_id")`. Asserted because the whole point of the picker is
    that the first BOQ of a chain decides the project for every revision after
    it, and nothing held that rule.
    """
    _mkproject("p1", "Sify Bangalore")
    _mkchain("p1")
    del STORE["boqs"]["rev1"]                     # revise rev0 through the form

    r = client.post("/boq/create",
                    data=_form(rev_no="1", supersedes="rev0", project_id=""))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    made = [b for b in STORE["boqs"].values() if b["id"] != "rev0"]
    assert len(made) == 1
    assert made[0]["project_id"] == "p1", \
        "a revision must carry its parent's project forward"


def test_a_revision_ignores_a_different_project_posted_on_the_form(client, clean):
    """
    The stated rule, now that the control exists to break it with: changing the
    project on one revision and not another would split a chain across two
    projects. The predecessor's value wins.
    """
    _mkproject("p1", "Sify Bangalore")
    _mkproject("p2", "Magarpatta Tower B")
    _mkchain("p1")
    del STORE["boqs"]["rev1"]

    r = client.post("/boq/create",
                    data=_form(rev_no="1", supersedes="rev0", project_id="p2"))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    made = [b for b in STORE["boqs"].values() if b["id"] != "rev0"]
    assert made[0]["project_id"] == "p1", \
        "the form must not be able to move one revision to another project"


# ═══ 3. A2 — attach and detach from the project page ═══════════════════════

def test_attaching_a_revised_boq_attaches_the_whole_chain(client, clean):
    """
    The rule already existed; this is the test on a REVISED BOQ that the brief
    for this pass asked for. Attaching the tip must attach the root too, or the
    chain is split across two projects and every claim summed across it is
    filed twice or not at all.
    """
    _mkproject("p1", "Sify Bangalore")
    root, tip = _mkchain("")

    r = client.post("/projects/view/p1",
                    data={"action": "attach_boq", "boq_id": tip})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert STORE["boqs"][tip]["project_id"] == "p1"
    assert STORE["boqs"][root]["project_id"] == "p1", \
        "attaching the tip left the root behind — the chain is split"


def test_detaching_clears_the_whole_chain(client, clean):
    """
    The mirror. A detach that cleared only the revision named would leave the
    rest of the chain pointing at a project the operator has just taken it off.
    """
    _mkproject("p1", "Sify Bangalore")
    root, tip = _mkchain("p1")

    r = client.post("/projects/view/p1",
                    data={"action": "detach_boq", "boq_id": tip})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert STORE["boqs"][tip]["project_id"] == ""
    assert STORE["boqs"][root]["project_id"] == "", \
        "detaching the tip left the root attached — the chain is split"


def test_detach_then_attach_elsewhere_is_the_correction_path(client, clean):
    """
    **Why detach has to exist at all.** There is no `/boq/edit` route, and the
    attach control offers only BOQs carrying no project — so without detach a
    BOQ filed against the wrong project is filed there permanently.
    """
    _mkproject("p1", "Sify Bangalore")
    _mkproject("p2", "Magarpatta Tower B")
    root, tip = _mkchain("p1")

    client.post("/projects/view/p1",
                data={"action": "detach_boq", "boq_id": tip})
    client.post("/projects/view/p2",
                data={"action": "attach_boq", "boq_id": tip})

    assert STORE["boqs"][tip]["project_id"] == "p2"
    assert STORE["boqs"][root]["project_id"] == "p2"


def test_detach_leaves_a_chain_member_on_another_project_alone(client, clean):
    """
    Only members currently on THIS project are cleared. A record belonging to
    somebody else's job is not silently rewritten by a page that is not looking
    at it — DOMAIN.md §6.
    """
    _mkproject("p1", "Sify Bangalore")
    _mkproject("p2", "Magarpatta Tower B")
    root, tip = _mkchain("p1")
    STORE["boqs"][root]["project_id"] = "p2"      # the odd one out

    r = client.post("/projects/view/p1",
                    data={"action": "detach_boq", "boq_id": tip})
    assert r.status_code == 302
    assert STORE["boqs"][tip]["project_id"] == ""
    assert STORE["boqs"][root]["project_id"] == "p2", \
        "detach reached into a project this page was not looking at"


def test_detaching_a_boq_that_is_not_attached_changes_nothing(client, clean):
    _mkproject("p1", "Sify Bangalore")
    _mkproject("p2", "Magarpatta Tower B")
    root, tip = _mkchain("p2")

    r = client.post("/projects/view/p1",
                    data={"action": "detach_boq", "boq_id": tip})
    assert r.status_code == 302
    # The flash rides the redirect as a form-encoded query parameter.
    assert "not+attached+to+this+project" in (r.headers.get("Location") or "")
    assert STORE["boqs"][tip]["project_id"] == "p2"
    assert STORE["boqs"][root]["project_id"] == "p2"


def test_detach_with_no_boq_selected_is_refused(client, clean):
    _mkproject("p1", "Sify Bangalore")
    _mkchain("p1")
    r = client.post("/projects/view/p1",
                    data={"action": "detach_boq", "boq_id": ""})
    assert r.status_code == 302
    assert "No+BOQ+selected" in (r.headers.get("Location") or "") \
        or "No%20BOQ%20selected" in (r.headers.get("Location") or "")
    assert STORE["boqs"]["rev0"]["project_id"] == "p1"


def test_the_project_page_offers_a_detach_control(client, clean):
    """The control, not only the branch behind it — the gap-33 lesson."""
    _mkproject("p1", "Sify Bangalore")
    _mkchain("p1")
    html = client.get("/projects/view/p1").get_data(as_text=True)
    assert 'value="detach_boq"' in html, \
        "the project page renders no detach control"
    assert "rev0" in html or "SF/BOQ/26-27/0001" in html


# ═══ 4. The write stays behind `project.edit` ══════════════════════════════

def test_detach_is_refused_without_project_edit(client, clean):
    """
    `/projects/view/<id>` is classified `project.view`, and its POST branch is
    raised to `project.edit` by a per-view guard. Detach is a write and must sit
    behind the same guard attach does — otherwise the read permission
    authorises unfiling every schedule on the project.
    """
    import auth

    _mkproject("p1", "Sify Bangalore")
    _mkchain("p1")

    real = auth.has_perm

    def _no_edit(perm, *a, **kw):
        return False if perm == "project.edit" else real(perm, *a, **kw)

    auth.has_perm = _no_edit
    try:
        r = client.post("/projects/view/p1",
                        data={"action": "detach_boq", "boq_id": "rev1"})
    finally:
        auth.has_perm = real

    assert r.status_code == 403, r.status_code
    assert STORE["boqs"]["rev1"]["project_id"] == "p1", \
        "a caller without project.edit detached a schedule"
    assert STORE["boqs"]["rev0"]["project_id"] == "p1"
