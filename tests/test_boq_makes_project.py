"""
A BOQ MAKES ITS OWN PROJECT — CLIENT_CHANGES.md §0 **fifty-eighth** block, item 1.

The client's report from the 28 October 2026 Yogesh meeting: *"when I write a
BoQ the project should get made, I should not have to open it first."* Before
this pass the *File under project* control on `/boq/create` sat on **None**,
so on a box where nobody had opened a project by hand every schedule was
filed nowhere, every project page was empty and the forty-seventh block's P&L
had nothing to stand on. ABOUT.md §7 gap 33 closed the control; this closes
the default.

**The three assertions that matter most:**

- `test_the_default_choice_is_new_project_from_this_boq` — the whole of the
  visible change. The option exists **and** carries `selected`.
- `test_one_job_spelled_two_ways_is_one_project` — two spellings of the same
  name make **one** project, through `pipeline.norm_name()`, the same
  comparison `/projects/create` refuses a near-duplicate with. Without it the
  default would manufacture a project per schedule and split every job.
- `test_a_revision_never_makes_a_second_project` — a revision takes its
  chain's project whatever the picker posted. This is the invariant the block
  states by name, and the one a careless default would break on every revise.

⚠ **Nothing here touches the attach / detach rule**, which already walked the
  whole revision chain and was correct; `tests/test_boq_project_link.py` owns
  it. What is new is where a project comes from when there is not one yet.
"""

import json

import pytest

import pipeline as P
import project as PJ
from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def clean():
    STORE["boqs"].clear()
    STORE["projects"].clear()
    yield
    STORE["boqs"].clear()
    STORE["projects"].clear()


def _form(rev_no="0", supersedes="", project_id=None,
          project="Sify Bangalore", account="Prudent Teqtis Pvt Ltd", **over):
    """`tests/test_boq_project_link.py::_form`'s body, so a failure here is
    about where the project comes from and nothing else."""
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


def _saved():
    """The one BOQ the POST under test wrote."""
    made = [b for b in STORE["boqs"].values() if b.get("ref")]
    assert len(made) == 1, f"expected 1 BOQ, got {len(made)}"
    return made[0]


def _mkproject(pid, name, client="Someone Else Pvt Ltd"):
    STORE["projects"][pid] = {
        "id": pid, "name": name, "norm_name": P.norm_name(name),
        "client": client, "notes": "", "site_address_id": "",
        "site_address": "", "created_at": "2026-10-01 09:00",
        "updated_at": "2026-10-01 09:00",
    }
    return pid


# ── The control and its default ────────────────────────────────────────────

def test_the_default_choice_is_new_project_from_this_boq(client, clean):
    """
    THE ASSERTION THAT MATTERS MOST (1 of 3). The option is on the page and it
    is the one that is `selected`.
    """
    html = client.get("/boq/create").get_data(as_text=True)
    assert f'value="{PJ.NEW_FROM_BOQ}"' in html, (
        "the New-project option is not on /boq/create at all")
    assert f'<option value="{PJ.NEW_FROM_BOQ}" selected>' in html, (
        "the New-project option is on the page but is not the default, which "
        "is the whole of item 1's visible change")


def test_the_old_choices_are_both_still_offered(client, clean):
    """Nothing that could be chosen before has been taken away."""
    _mkproject("p-existing", "Tower B")
    html = client.get("/boq/create").get_data(as_text=True)
    assert 'value=""' in html and "None: not filed under a project" in html
    assert 'value="p-existing"' in html and "Tower B" in html


def test_an_explicit_choice_is_not_reset_to_new(client, clean):
    """
    `?project_id=` — the project page's *Raise new BOQ* button — still wins,
    and the New option is then not `selected`. A default that overrode a
    deliberate pick would make that button do the wrong thing.
    """
    _mkproject("p-existing", "Tower B")
    html = client.get("/boq/create?project_id=p-existing").get_data(as_text=True)
    assert '<option value="p-existing" selected>' in html
    assert f'<option value="{PJ.NEW_FROM_BOQ}" selected>' not in html


# ── What the POST stores ───────────────────────────────────────────────────

def test_the_sentinel_makes_a_project_from_the_boqs_own_fields(client, clean):
    """Name from `project_name`, client from `account_name` — the block's
    wording — and the normalised name stored with them."""
    client.post("/boq/create", data=_form(project_id=PJ.NEW_FROM_BOQ),
                follow_redirects=False)
    assert len(STORE["projects"]) == 1
    proj = next(iter(STORE["projects"].values()))
    assert proj["name"] == "Sify Bangalore"
    assert proj["client"] == "Prudent Teqtis Pvt Ltd"
    assert proj["norm_name"] == P.norm_name("Sify Bangalore")
    assert _saved()["project_id"] == proj["id"], (
        "the project was made but the schedule was not filed under it")


def test_the_new_project_has_no_site_and_is_not_guessed(client, clean):
    """
    The BOQ's `site_location` is free text; a project's site is an
    address-book JOIN KEY. Guessing one from the other is the fuzzy match this
    repo refuses everywhere, so both keys are written BLANK and `/projects/view`
    tells the operator to link one.
    """
    client.post("/boq/create",
                data=_form(project_id=PJ.NEW_FROM_BOQ,
                           site_location="Banglore, Karnatka"))
    proj = next(iter(STORE["projects"].values()))
    assert proj[PJ.SITE_ADDRESS_ID_FIELD] == ""
    assert proj["site_address"] == ""
    assert PJ.is_legacy_site(proj) is False, (
        "a blank site must not read as a legacy free-text site — the two have "
        "different fixes and different messages")


def test_one_job_spelled_two_ways_is_one_project(client, clean):
    """
    THE ASSERTION THAT MATTERS MOST (2 of 3). Two schedules, two spellings of
    one name, ONE project — and the second schedule joins the first's project
    rather than starting a rival.
    """
    client.post("/boq/create",
                data=_form(project_id=PJ.NEW_FROM_BOQ, project="Sify Bangalore"))
    first = next(iter(STORE["projects"].values()))["id"]
    STORE["boqs"].clear()
    client.post("/boq/create",
                data=_form(project_id=PJ.NEW_FROM_BOQ, project="sify   BANGALORE"))
    assert len(STORE["projects"]) == 1, (
        f"{len(STORE['projects'])} projects for one job: "
        f"{sorted(p['name'] for p in STORE['projects'].values())}")
    assert _saved()["project_id"] == first


def test_an_existing_project_is_reused_and_never_edited(client, clean):
    """Its client is somebody's decision. A BOQ naming the same job does not
    get to overwrite it."""
    _mkproject("p-sify", "Sify Bangalore", client="Original Client Ltd")
    client.post("/boq/create",
                data=_form(project_id=PJ.NEW_FROM_BOQ, project="Sify Bangalore",
                           account="Someone Typed This Instead"))
    assert len(STORE["projects"]) == 1
    assert STORE["projects"]["p-sify"]["client"] == "Original Client Ltd"
    assert _saved()["project_id"] == "p-sify"


def test_choosing_none_still_files_the_schedule_nowhere(client, clean):
    """The option is still there and still means what it says."""
    client.post("/boq/create", data=_form(project_id=""))
    assert STORE["projects"] == {}
    assert _saved()["project_id"] == ""


def test_choosing_an_existing_project_is_unchanged(client, clean):
    _mkproject("p-tower", "Tower B")
    client.post("/boq/create", data=_form(project_id="p-tower"))
    assert len(STORE["projects"]) == 1
    assert _saved()["project_id"] == "p-tower"


def test_a_blank_project_name_makes_no_project(client, clean):
    """`project_name` is required by the form; if it ever is not, a project
    with no name is not made in its place."""
    pid, created = PJ.ensure_from_boq("   ", "Prudent Teqtis Pvt Ltd")
    assert (pid, created) == ("", False)
    assert STORE["projects"] == {}


# ── The revision rule ──────────────────────────────────────────────────────

def _mkchain(pid="", n=2):
    """A revision chain of `n` links, every member carrying `pid`."""
    ids = []
    for rev in range(n):
        bid = f"rev{rev}"
        STORE["boqs"][bid] = {
            "id": bid, "ref": "", "fy": "26-27", "date": "2026-08-12",
            "rev_no": rev, "supersedes": f"rev{rev - 1}" if rev else "",
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
        ids.append(bid)
    return ids


def test_a_revision_never_makes_a_second_project(client, clean):
    """
    THE ASSERTION THAT MATTERS MOST (3 of 3). The picker posts the sentinel on
    a revision — which it will, because it defaults to it — and the revision
    still lands on its chain's project. **No second project is written.**
    """
    _mkproject("p-sify", "Sify Bangalore")
    _mkchain("p-sify", n=1)
    client.post("/boq/create",
                data=_form(rev_no="1", supersedes="rev0",
                           project_id=PJ.NEW_FROM_BOQ))
    assert len(STORE["projects"]) == 1, (
        "a revision manufactured a project of its own, which splits the "
        "chain's claims across two P&Ls")
    assert _saved()["project_id"] == "p-sify"


def test_a_revision_takes_the_CHAIN_ROOT_not_its_predecessor(client, clean):
    """
    The tightening. A hand-edited middle revision pointing elsewhere does not
    drag the new revision with it: the ROOT is the answer, which is the one
    reading that cannot put two members of one chain on two projects.
    """
    _mkproject("p-root", "Root Project")
    _mkproject("p-stray", "Stray Project")
    _mkchain("p-root", n=2)
    STORE["boqs"]["rev1"]["project_id"] = "p-stray"      # the hand edit
    client.post("/boq/create",
                data=_form(rev_no="2", supersedes="rev1",
                           project_id=PJ.NEW_FROM_BOQ))
    assert _saved()["project_id"] == "p-root"
    assert len(STORE["projects"]) == 2, "no third project may be invented"


def test_a_revision_of_an_unattached_chain_stays_unattached(client, clean):
    """
    A chain on no project revises to no project. The sentinel is ignored on a
    revision, so revising cannot be a back door to attaching one — attach and
    detach on `/projects/view` stay the only way, because they move the WHOLE
    chain and this would move one member.
    """
    _mkchain("", n=1)
    client.post("/boq/create",
                data=_form(rev_no="1", supersedes="rev0",
                           project_id=PJ.NEW_FROM_BOQ))
    assert STORE["projects"] == {}
    assert _saved()["project_id"] == ""


def test_a_chain_attached_only_at_its_tip_is_still_found(client, clean):
    """
    `project_of_chain()` falls back to the record's own tag when the root
    carries none, so a half-attached chain is not reported as unattached.
    """
    _mkproject("p-tip", "Tip Only")
    _mkchain("", n=2)
    STORE["boqs"]["rev1"]["project_id"] = "p-tip"
    assert PJ.project_of_chain("rev1") == "p-tip"


# ── The chain walk itself ──────────────────────────────────────────────────

def test_chain_root_walks_all_the_way_back(clean):
    _mkchain("p", n=4)
    for bid in ("rev0", "rev1", "rev2", "rev3"):
        assert PJ.chain_root_id(bid) == "rev0"


def test_chain_root_of_an_unknown_id_is_blank(clean):
    assert PJ.chain_root_id("nope") == ""
    assert PJ.chain_root_id("") == ""
    assert PJ.project_of_chain("nope") == ""


def test_chain_root_survives_a_cycle_in_the_data(clean):
    """
    `supersedes` is written by a form and nothing validates that the chain is
    acyclic. A hand-edited pair pointing at each other must not hang the
    request — it returns the oldest record the walk could reach.
    """
    _mkchain("p", n=2)
    STORE["boqs"]["rev0"]["supersedes"] = "rev1"      # the cycle
    assert PJ.chain_root_id("rev1") in ("rev0", "rev1")


def test_a_dangling_supersedes_stops_the_walk(clean):
    """A revision whose predecessor was deleted is its own root rather than
    an exception."""
    _mkchain("p", n=1)
    STORE["boqs"]["rev0"]["supersedes"] = "deleted-long-ago"
    assert PJ.chain_root_id("rev0") == "rev0"
