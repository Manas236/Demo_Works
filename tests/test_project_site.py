"""
A project takes its site from the ADDRESS BOOK — the link, the snapshot, the drift.

`projects.site_address` was free text somebody typed until 30 August 2026, which
is why this database holds *"Banglore, Karnataka"* on two projects and
*"Bangalore, Karnataka"* on a third. One place, two spellings, on three of the
four projects that name a site at all. **A project's site is a join key and free
text cannot join.**

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **THE SNAPSHOT AND THE LINK MOVE TOGETHER, OR NEITHER DOES.** A save that
   wrote the id and left `site_address` alone would manufacture the exact
   disagreement `site_drift()` exists to report.
2. ⚠ **EXISTING RECORDS ARE UNHARMED BY CONSTRUCTION.** Every current reader —
   the register's SITE column, `projectview.py` — goes on reading
   `site_address`, which is now the label snapshot. A legacy record renders
   exactly as it did.
3. ⚠ **A LEGACY STRING IS NEVER REWRITTEN BY THE FORM.** `Banglore` stays
   `Banglore` until a person picks. Saving one requires a pick; leaving the
   picker alone does not silently write the id-less shape back.
4. ⚠ **THE DRIFT IS REPORTED, NEVER RECONCILED.** `ra.party_drift()`'s rule and
   DOMAIN.md §6's: surface it, name it, never silently correct it.
5. **The picker has no free-text fallback, and an "Add a new address" link
   beside it.** `challan.py`'s consignee keeps a fallback and this deliberately
   does not — the tie-breaker is that a site store worth four months is not
   worth an address-book entry, but a join key has to be one. Without the link,
   a user in front of an unfiled site has no move at all.
6. **Only `SITE_TYPES` addresses may be a project's site**, enforced on the
   POST and not only in the option list. A vendor is somebody we buy from.

⚠ **Do not weaken any of these to make a red suite green.** If (3) fails, a
project silently loses the only record of where its work happened.
"""

import pathlib

import pytest

import address as AD
import project as PJ
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

_MINTED = set()


@pytest.fixture(autouse=True)
def _clean():
    STORE.setdefault("projects", {}).clear()
    _MINTED.clear()
    yield
    STORE.setdefault("projects", {}).clear()
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


def _addr(label, atype="site", aid=None):
    aid = aid or f"paddr-{label.lower().replace(' ', '-').replace(',', '')}"
    _MINTED.add(aid)
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": atype,
        "contact_name": "", "company": "", "line1": "1 Site Road",
        "line2": "", "landmark": "", "city": "Bengaluru",
        "state": "Karnataka", "pincode": "560066", "country": "India",
        "phone": "", "email": "", "gstin": "",
    }
    return aid


def _legacy(pid="p-old", site="Banglore, Karnataka"):
    """A project as the register wrote it when `site_address` was free text."""
    STORE.setdefault("projects", {})[pid] = {
        "id": pid, "name": "Sify Bangalore", "norm_name": "sify bangalore",
        "client": "Prudent Teqtis", "site_address": site, "notes": "",
        "created_at": "2026-08-01 09:00", "updated_at": "2026-08-01 09:00"}
    return STORE["projects"][pid]


def _form(**over):
    form = {"name": "Sify Bangalore", "client": "Prudent Teqtis",
            "site_address_id": "", "notes": ""}
    form.update(over)
    return form


# ═══ 1. CREATE writes both keys ════════════════════════════════════════════

def test_creating_with_a_picked_site_writes_the_id_AND_the_snapshot(client):
    aid = _addr("Whitefield, Karnataka")
    client.post("/projects/create", data=_form(site_address_id=aid),
                follow_redirects=False)
    p = next(iter(STORE["projects"].values()))
    assert p[PJ.SITE_ADDRESS_ID_FIELD] == aid, "the link was not written"
    assert p["site_address"] == "Whitefield, Karnataka", (
        "the label snapshot was not written — every existing reader reads this "
        "field and would render a blank")


def test_creating_without_a_site_leaves_both_keys_empty(client):
    client.post("/projects/create", data=_form(name="No Site Yet"),
                follow_redirects=False)
    p = next(iter(STORE["projects"].values()))
    assert p[PJ.SITE_ADDRESS_ID_FIELD] == ""
    assert p["site_address"] == ""


def test_the_form_offers_no_free_text_site_box(client):
    _addr("Whitefield, Karnataka")
    for url in ("/projects/create",):
        html = client.get(url).get_data(as_text=True)
        assert 'name="site_address_id"' in html
        assert '<select id="site_address_id"' in html
        assert 'input type="text" id="site_address"' not in html, (
            "the free-text site box is still on the form — a join key cannot "
            "be typed")


def test_the_form_carries_an_add_a_new_address_link(client):
    """
    ⚠ **Required, not decoration.** Without it a user standing in front of a
    project whose site is not in the book has no move at all, and a picker with
    no escape is worse than the free text it replaced.
    """
    _addr("Whitefield, Karnataka")
    for url in ("/projects/create", "/projects/edit/p-old"):
        _legacy()
        html = client.get(url).get_data(as_text=True)
        assert "/address/add" in html, f"{url} offers no way to add an address"


def test_the_picker_offers_sites_and_offices_only(client):
    site = _addr("Whitefield, Karnataka", "site")
    office = _addr("Head Office", "office")
    vendor = _addr("Sanghvi Steel", "vendor")
    html = client.get("/projects/create").get_data(as_text=True)
    assert site in html and office in html
    assert vendor not in html, (
        "a vendor was offered as a project's site — a vendor is somebody we "
        "buy from, not a place work happens")


def test_a_non_site_address_is_refused_on_the_POST(client):
    """The option list is not the guard; a hand-made POST reaches the same rule."""
    vendor = _addr("Sanghvi Steel", "vendor")
    resp = client.post("/projects/create", data=_form(site_address_id=vendor))
    assert not STORE["projects"], "a vendor was stored as a project's site"
    assert "not a site or an office" in resp.get_data(as_text=True)


def test_an_unknown_address_id_is_refused(client):
    resp = client.post("/projects/create",
                       data=_form(site_address_id="no-such-address"))
    assert not STORE["projects"]
    assert "no longer in the address book" in resp.get_data(as_text=True)


# ═══ 2. The LEGACY branch — the string is never rewritten ══════════════════

def test_a_legacy_project_renders_its_string_marked_as_legacy(client):
    _addr("Bangalore, Karnataka")
    _legacy()
    html = client.get("/projects/edit/p-old").get_data(as_text=True)
    assert "Banglore, Karnataka" in html, "the recorded string was not shown"
    assert "free text" in html, "it was not marked as legacy"


def test_a_legacy_projects_picker_opens_EMPTY(client):
    """
    ⚠ **Nothing is guessed at.** `Bangalore, Karnataka` is in the book and is
    one letter away; pre-selecting it is the fuzzy match this repository has
    already paid for once (ABOUT.md §2h).
    """
    near = _addr("Bangalore, Karnataka")
    _legacy()
    html = client.get("/projects/edit/p-old").get_data(as_text=True)
    assert f'value="{near}" selected' not in html
    assert "selected" not in html.split('name="site_address_id"')[1].split("</select>")[0]


def test_saving_a_legacy_project_REQUIRES_a_pick(client):
    _addr("Bangalore, Karnataka")
    _legacy()
    resp = client.post("/projects/edit/p-old", data=_form(site_address_id=""))
    p = STORE["projects"]["p-old"]
    assert p["site_address"] == "Banglore, Karnataka", (
        "the legacy string was cleared by a save that named no address")
    assert not p.get(PJ.SITE_ADDRESS_ID_FIELD)
    assert "free-text string" in resp.get_data(as_text=True)


def test_the_legacy_string_is_replaced_by_the_LABEL_when_it_is_mapped(client):
    aid = _addr("Bangalore, Karnataka")
    _legacy()
    client.post("/projects/edit/p-old", data=_form(site_address_id=aid),
                follow_redirects=False)
    p = STORE["projects"]["p-old"]
    assert p[PJ.SITE_ADDRESS_ID_FIELD] == aid
    assert p["site_address"] == "Bangalore, Karnataka", (
        "the snapshot did not follow the pick — the two copies would disagree "
        "from the moment they were written")


def test_the_register_and_the_view_page_render_a_legacy_record_unchanged(client):
    """
    ⚠ **Existing records unharmed BY CONSTRUCTION.** Both readers go on reading
    `site_address`, which is why nothing had to be migrated for them.
    """
    _legacy()
    assert "Banglore, Karnataka" in client.get("/projects/").get_data(as_text=True)
    assert "Banglore, Karnataka" in (
        client.get("/projects/view/p-old").get_data(as_text=True))


# ═══ 3. DRIFT is reported, never reconciled ════════════════════════════════

def test_no_drift_when_the_two_copies_agree():
    aid = _addr("Whitefield")
    p = _legacy(site="Whitefield")
    p[PJ.SITE_ADDRESS_ID_FIELD] = aid
    assert PJ.site_drift(p) is None


def test_editing_the_address_raises_drift_and_the_snapshot_does_NOT_move(client):
    aid = _addr("Whitefield")
    p = _legacy(site="Whitefield")
    p[PJ.SITE_ADDRESS_ID_FIELD] = aid
    STORE["addresses"][aid]["label"] = "Whitefield Phase 2"

    assert PJ.site_drift(p) == ("Whitefield", "Whitefield Phase 2")
    assert p["site_address"] == "Whitefield", (
        "the snapshot was silently reconciled — DOMAIN.md §6 says surface it, "
        "name it, never silently correct it")

    html = client.get("/projects/view/p-old").get_data(as_text=True)
    assert "pm-drift" in html, "no divergence band was rendered"
    assert "Whitefield Phase 2" in html and "Whitefield" in html


def test_a_dangling_id_is_reported_as_its_own_case(client):
    p = _legacy(site="Whitefield")
    p[PJ.SITE_ADDRESS_ID_FIELD] = "address-that-was-deleted"
    assert PJ.site_drift(p) == ("Whitefield", "")
    html = client.get("/projects/view/p-old").get_data(as_text=True)
    assert "no longer in the book" in html


def test_a_legacy_record_reports_no_drift_but_says_so_on_the_page(client):
    p = _legacy()
    assert PJ.site_drift(p) is None, (
        "a record with no id has nothing to compare against; reporting drift "
        "on it would name a disagreement that does not exist")
    html = client.get("/projects/view/p-old").get_data(as_text=True)
    assert "free text from before the address book" in html


def test_an_ARCHIVED_address_still_resolves_and_raises_no_drift(client):
    aid = _addr("Whitefield")
    p = _legacy(site="Whitefield")
    p[PJ.SITE_ADDRESS_ID_FIELD] = aid
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    assert PJ.site_label_of(aid) == "Whitefield"
    assert PJ.site_drift(p) is None, (
        "archiving an address made every project pointing at it look adrift — "
        "archiving takes it out of the pickers, not away from the records")


def test_re_saving_the_project_takes_the_new_label(client):
    aid = _addr("Whitefield")
    p = _legacy(site="Whitefield")
    p[PJ.SITE_ADDRESS_ID_FIELD] = aid
    STORE["addresses"][aid]["label"] = "Whitefield Phase 2"
    client.post("/projects/edit/p-old", data=_form(site_address_id=aid),
                follow_redirects=False)
    assert STORE["projects"]["p-old"]["site_address"] == "Whitefield Phase 2"
    assert PJ.site_drift(STORE["projects"]["p-old"]) is None


# ═══ 4. Clearing, and the empty book ═══════════════════════════════════════

def test_clearing_the_pick_on_a_NON_legacy_project_clears_both_keys(client):
    aid = _addr("Whitefield")
    p = _legacy(site="Whitefield")
    p[PJ.SITE_ADDRESS_ID_FIELD] = aid
    client.post("/projects/edit/p-old", data=_form(site_address_id=""),
                follow_redirects=False)
    after = STORE["projects"]["p-old"]
    assert after[PJ.SITE_ADDRESS_ID_FIELD] == ""
    assert after["site_address"] == ""


def test_an_empty_book_says_so_rather_than_offering_an_empty_select(client):
    """
    `picker_options()` no longer seeds, so this is a state a form can genuinely
    open in. A `<select>` holding one placeholder is not an answer.
    """
    saved = dict(STORE["addresses"])
    try:
        STORE["addresses"].clear()
        html = client.get("/projects/create").get_data(as_text=True)
        assert "No sites in the address book" in html
        assert "/address/add" in html
        assert '<select id="site_address_id"' not in html
    finally:
        STORE["addresses"].clear()
        STORE["addresses"].update(saved)


# ═══ 5. The join, and what it does NOT do ══════════════════════════════════

def test_the_project_is_the_end_of_the_arrow_that_carries_the_id():
    """
    ABOUT.md §4's three ways out: `address.project_id` is the one it calls the
    wrong shape, because one site can carry work for more than one project.
    """
    aid = _addr("Whitefield")
    assert not any(k.startswith("project") for k in STORE["addresses"][aid])


def test_one_site_may_carry_more_than_one_project():
    """
    ⚠ **No guard is built on this, deliberately.** The client has said one
    project = one site; he has **not** said one site = one project, and the live
    data already has two projects on one string. The count is evidence for a
    later pass (C6), not a constraint.
    """
    aid = _addr("Whitefield")
    for pid in ("p-1", "p-2"):
        STORE["projects"][pid] = {
            "id": pid, "name": f"Project {pid}", "norm_name": f"project {pid}",
            "client": "", "site_address": "Whitefield",
            PJ.SITE_ADDRESS_ID_FIELD: aid, "notes": "",
            "created_at": "", "updated_at": ""}
    refs = [r for r in AD.references_of(aid) if r["collection"] == "projects"]
    assert len(refs) == 2, "two projects on one site was refused somewhere"


def test_projectview_still_shows_no_margin_total_or_net():
    """
    The standing prohibition at the top of `projectview.py`, restated here
    because the divergence band is exactly the kind of change that reaches into
    that file and could be tempted to take more with it.
    """
    src = (REPO / "projectview.py").read_text(encoding="utf8")
    head = src[:src.index("projectview_bp = Blueprint")]
    for word in ("no revenue total", "no cost total", "no margin", "no profit",
                 "no net", "no balance"):
        assert word in head, f"the prohibition lost {word!r}"


def test_project_py_reads_SITE_TYPES_from_address_and_never_redefines_it():
    import ast
    tree = ast.parse((REPO / "project.py").read_text(encoding="utf8"))
    names = [t.id for n in tree.body if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)]
    assert "SITE_TYPES" not in names, (
        "project.py defines its own SITE_TYPES — two pickers that can disagree "
        "about what counts as a site is the defect address.py owns it to stop")
    assert PJ.AD.SITE_TYPES is AD.SITE_TYPES
