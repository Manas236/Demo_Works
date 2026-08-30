"""
The address book is a MASTER — references, delete, archive, edit, type lock.

`address.py`'s own docstring said *"nothing else in the app reads
STORE['addresses']"* until 30 August 2026, and `delete_address()` said in terms
that *"there is no integrity check to run here"*. Both were true when they were
written. Neither had been true for weeks: six collections point into the book,
and deleting a row dangled every reference silently, with nothing on any screen
saying so.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **`references_of()` MATCHES ON BOTH THE ID AND THE SNAPSHOT STRING.** Some
   live references are strings, because those fields were free text before the
   pickers arrived and the backfills deliberately left an unmatched string
   exactly as it stood. A guard reading only the id passes a legacy record
   straight through and deletes the address underneath it.
2. ⚠ **NOTHING IS FUZZY-MATCHED.** `banglore` is not `Banglore`. The comparison
   is `strip()` and nothing else — `tools/backfill_site_links.py`'s rule and
   `po_parts.py`'s lesson (ABOUT.md §2h).
3. ⚠ **A BLANK SNAPSHOT MATCHES NOTHING.** An address with no company would
   otherwise claim every record whose company field is empty, and the guard
   would refuse every deletion in the book while looking like it worked.
4. **The refusal NAMES the records.** A refusal that does not say what is
   blocking it is a dead end — `ra.party_lock_bills()`'s finding, and the guard
   is on the POST as well as the GET.
5. ⚠ **ARCHIVE IS THE ESCAPE, and `active` ABSENT MEANS ACTIVE.** A
   delete-refusal with no archive is a trap rather than a guard. Six live
   records carry no `active` key; a reading that treated absence as archived
   would empty every picker in the application at once.
6. **An archived address still resolves, and is still offered as the CURRENT
   selection** — otherwise an edit form silently drops the vendor a record
   already carries.
7. ⚠ **EDITING A REFERENCED ADDRESS IS ALLOWED AND LOGGED, BY USER ID.**
   `Banglore` is misspelled on the live database and nothing repoints a record
   onto a different address, so a freeze would make it permanent.
   `purchase.reprice_log` stores a display name and that is a known open gap;
   this stores the id and resolves it at render time.
8. **`type` is the one locked field**, because it is what the pickers filter on.

⚠ **Do not weaken any of these to make a red suite green.** If (1) or (3) fails,
an address can be deleted out from under a record that names it, or no address
can be deleted at all.
"""

import pathlib

import pytest

import address as AD
import employee as EMP
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

_MINTED = set()

_TOUCHED = ("projects", "employees", "attendance",
            "purchase_orders", "purchases", "delivery_challans")


@pytest.fixture(autouse=True)
def _clean():
    for key in _TOUCHED:
        STORE.setdefault(key, {}).clear()
    _MINTED.clear()
    yield
    for key in _TOUCHED:
        STORE.setdefault(key, {}).clear()
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


def _addr(label, atype="site", aid=None, **over):
    aid = aid or f"addr-{label.lower().replace(' ', '-').replace(',', '')}"
    _MINTED.add(aid)
    rec = {
        "id": aid, "label": label, "type": atype,
        "contact_name": "", "company": "", "line1": "1 Site Road",
        "line2": "", "landmark": "", "city": "Bengaluru",
        "state": "Karnataka", "pincode": "560066", "country": "India",
        "phone": "", "email": "", "gstin": "",
    }
    rec.update(over)
    STORE.setdefault("addresses", {})[aid] = rec
    return aid


def _project(pid="p-1", **over):
    rec = {"id": pid, "name": "Sify Bangalore", "norm_name": "sify bangalore",
           "client": "Prudent Teqtis", "site_address": "", "site_address_id": "",
           "notes": "", "created_at": "2026-08-30 10:00",
           "updated_at": "2026-08-30 10:00"}
    rec.update(over)
    STORE.setdefault("projects", {})[pid] = rec
    return rec


# ═══ 1. references_of() — the function every guard reads ═══════════════════

def test_an_unreferenced_address_has_no_references():
    aid = _addr("Whitefield")
    assert AD.references_of(aid) == []


def test_a_project_pointing_by_id_is_a_reference():
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    refs = AD.references_of(aid)
    assert [r["collection"] for r in refs] == ["projects"]
    assert refs[0]["how"] == "id"
    assert refs[0]["kind"] == "Project"
    assert "Sify Bangalore" in refs[0]["label"]


def test_a_project_pointing_by_SNAPSHOT_STRING_is_a_reference():
    """
    ⚠ **The half a naive guard misses.** A project written before the picker
    carries the string and no id at all, and deleting the address it names
    leaves the string behind with nothing under it.
    """
    aid = _addr("Banglore, Karnataka")
    _project(site_address="Banglore, Karnataka", site_address_id="")
    refs = AD.references_of(aid)
    assert len(refs) == 1, "a legacy project naming this address by string was missed"
    assert refs[0]["how"] == "label"


def test_an_employee_and_an_attendance_marking_are_references():
    aid = _addr("Hinjewadi")
    STORE["employees"]["e-1"] = {"id": "e-1", "name": "Ramesh Patil",
                                 "code": "SF-014", "site": "Hinjewadi",
                                 "site_address_id": aid}
    STORE["attendance"]["a-1"] = {"id": "a-1", "employee_name": "Ramesh Patil",
                                  "date": "2026-08-29", "site": "Hinjewadi",
                                  "site_address_id": ""}
    kinds = sorted(r["kind"] for r in AD.references_of(aid))
    assert kinds == ["Attendance", "Employee"]


def test_the_three_vendor_and_consignee_collections_are_references():
    aid = _addr("Sanghvi Steel", atype="vendor", company="Sanghvi Steel & Pipes")
    STORE["purchase_orders"]["d-1"] = {"id": "d-1", "ref": "DPO-0007",
                                       "vendor_id": aid, "vendor_name": ""}
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "PO-0011",
                                  "vendor_id": "", "vendor_name": "Sanghvi Steel & Pipes"}
    STORE["delivery_challans"]["dc-1"] = {"id": "dc-1", "ref": "DC-0003",
                                          "consignee_id": aid, "consignee_name": ""}
    refs = AD.references_of(aid)
    assert sorted(r["kind"] for r in refs) == [
        "Delivery challan", "Draft PO", "Purchase order"]
    by_kind = {r["kind"]: r["how"] for r in refs}
    assert by_kind["Purchase order"] == "label", (
        "a PO carrying only the vendor's company name was not matched — "
        "purchase.py writes `company or label` and nothing else")


def test_the_snapshot_comparison_is_EXACT_and_never_fuzzy():
    """
    ⚠ **`banglore` is not `Banglore`.** No casefolding, no whitespace
    collapsing, no prefix match. This is `tools/backfill_site_links.py`'s rule,
    which exists because a wrong automatic match looks exactly like a right one.
    """
    aid = _addr("Banglore, Karnataka")
    for near in ("banglore, karnataka", "Banglore,  Karnataka",
                 "Bangalore, Karnataka", "Banglore"):
        STORE["projects"].clear()
        _project(site_address=near, site_address_id="")
        assert AD.references_of(aid) == [], (
            f"{near!r} was matched against 'Banglore, Karnataka' — something "
            f"here is fuzzy-matching")


def test_leading_and_trailing_WHITESPACE_is_the_one_thing_stripped():
    aid = _addr("Whitefield")
    _project(site_address="  Whitefield  ", site_address_id="")
    assert len(AD.references_of(aid)) == 1


def test_a_BLANK_snapshot_field_matches_nothing():
    """
    ⚠ **The vacuity that would refuse every deletion in the book.** An address
    with no company and no contact name must not claim the dozens of records
    whose own snapshot fields are empty strings.
    """
    aid = _addr("Whitefield", company="", contact_name="")
    _project(site_address="", site_address_id="")
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "PO-0011",
                                  "vendor_id": "", "vendor_name": ""}
    assert AD.references_of(aid) == []


def test_references_of_answers_nothing_for_a_blank_or_unknown_id():
    _project(site_address="Whitefield", site_address_id="")
    assert AD.references_of("") == []
    assert AD.references_of(None) == []
    assert AD.references_of("no-such-address") == []


def test_every_collection_that_points_at_the_book_is_in_REFERENCE_SOURCES():
    """
    The inventory, asserted rather than assumed. A seventh collection growing a
    vendor or site link and not joining this tuple is a silent hole in every
    guard below.
    """
    covered = {c for c, *_ in AD.REFERENCE_SOURCES}
    assert covered == {"projects", "employees", "attendance",
                       "purchase_orders", "purchases", "delivery_challans"}
    for coll, id_field, snap_field, kind, label_fields, endpoint in AD.REFERENCE_SOURCES:
        assert coll in STORE, f"{coll} is not a collection in the store"
        assert id_field and snap_field and kind and label_fields and endpoint


# ═══ 2. DELETE is refused, and the refusal names the records ═══════════════

def test_the_delete_confirmation_names_the_blocking_records(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    html = client.get(f"/address/delete/{aid}").get_data(as_text=True)
    assert "cannot be deleted" in html
    assert "Sify Bangalore" in html, (
        "the refusal did not name the record blocking it — a refusal that does "
        "not say what is blocking it is a dead end")
    assert "Archive" in html, "the refusal offered no alternative"


def test_the_delete_POST_is_refused_and_destroys_nothing(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    client.post(f"/address/delete/{aid}", follow_redirects=False)
    assert aid in STORE["addresses"], (
        "a referenced address was destroyed by a POST — the guard is on the "
        "confirmation page only, which is not a guard")


def test_an_unreferenced_address_is_still_hard_deletable(client):
    """The cleanup path for a duplicate. The archive does not replace it."""
    aid = _addr("Typo Site")
    client.post(f"/address/delete/{aid}", follow_redirects=False)
    assert aid not in STORE["addresses"]


def test_the_delete_page_says_the_check_was_actually_run(client):
    aid = _addr("Typo Site")
    html = client.get(f"/address/delete/{aid}").get_data(as_text=True)
    assert "by id and by name" in html


# ═══ 3. ARCHIVE — the escape a refused delete needs ════════════════════════

def test_absent_active_means_ACTIVE():
    """
    ⚠ **The reading that would empty every picker in the application.** Six live
    records and every seeded one carry no `active` key.
    """
    aid = _addr("Whitefield")
    assert "active" not in STORE["addresses"][aid]
    assert AD.is_active(STORE["addresses"][aid]) is True
    assert aid in AD.picker_options(only_types=AD.SITE_TYPES)


def test_an_archived_address_leaves_every_picker(client):
    aid = _addr("Whitefield")
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    assert AD.is_active(STORE["addresses"][aid]) is False
    assert aid not in AD.picker_options(only_types=AD.SITE_TYPES)
    assert aid not in AD.picker_options()
    assert aid not in EMP.site_options()


def test_an_archived_address_STILL_RESOLVES_for_existing_records(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    assert STORE["addresses"][aid]["label"] == "Whitefield"
    assert EMP.site_label_of(aid) == "Whitefield"
    assert len(AD.references_of(aid)) == 1


def test_an_archived_address_is_still_offered_as_the_CURRENT_selection(client):
    """
    Otherwise an edit form re-rendering a record whose vendor was archived
    afterwards silently drops the vendor it already carries.
    """
    aid = _addr("Sanghvi Steel", atype="vendor")
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    opts = AD.picker_options(only_types=("vendor",), selected=aid)
    assert aid in opts, "the record's own selection vanished from its edit form"
    assert "(archived)" in opts, "it was offered with no sign it is archived"


def test_un_archiving_puts_it_back(client):
    aid = _addr("Whitefield")
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    client.post(f"/address/unarchive/{aid}", follow_redirects=False)
    assert AD.is_active(STORE["addresses"][aid]) is True
    assert aid in AD.picker_options(only_types=AD.SITE_TYPES)


def test_archive_and_unarchive_refuse_a_GET(client):
    aid = _addr("Whitefield")
    assert client.get(f"/address/archive/{aid}").status_code == 405
    assert client.get(f"/address/unarchive/{aid}").status_code == 405
    assert AD.is_active(STORE["addresses"][aid]) is True


def test_the_address_page_offers_the_archive_and_names_the_references(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    html = client.get(f"/address/view/{aid}").get_data(as_text=True)
    assert "Sify Bangalore" in html
    assert f"/address/archive/{aid}" in html
    assert "cannot be deleted" in html


def test_the_address_page_says_when_nothing_points_at_it(client):
    aid = _addr("Typo Site")
    html = client.get(f"/address/view/{aid}").get_data(as_text=True)
    assert "Nothing points at this address" in html


# ═══ 4. EDIT is allowed, and logged BY USER ID ═════════════════════════════

def _edit_form(addr, **over):
    form = {k: addr.get(k, "") for k in
            ("label", "type", "contact_name", "company", "line1", "line2",
             "landmark", "city", "state", "pincode", "phone", "email", "gstin")}
    form.update(over)
    return form


def test_a_referenced_address_can_still_be_edited(client):
    """
    ⚠ **The reason the edit is not frozen.** `Banglore` is misspelled on the
    live database and nothing in this application repoints a record onto a
    different address; a freeze makes the misspelling permanent.
    """
    aid = _addr("Banglore, Karnataka")
    _project(site_address="Banglore, Karnataka", site_address_id=aid)
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}",
                data=_edit_form(addr, label="Bangalore, Karnataka"),
                follow_redirects=False)
    assert STORE["addresses"][aid]["label"] == "Bangalore, Karnataka"


def test_the_edit_log_records_a_USER_ID_and_not_a_display_name(client):
    """
    ⚠ **`purchase.reprice_log` stores `display_name or username` and that is a
    known open gap**: rename the user and the history restates itself, delete
    them and it names nobody. This does not repeat it.
    """
    import auth
    from conftest import TEST_USER

    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr, city="Bangalore"),
                follow_redirects=False)

    log = STORE["addresses"][aid][AD.EDIT_LOG_FIELD]
    assert len(log) == 1
    entry = log[0]
    assert entry["by_user_id"] == auth.find_user(TEST_USER)["id"]
    assert entry["by_user_id"] != "Test Owner", "a display name was stored"
    assert entry["at"]
    assert entry["changes"] == [{"field": "city", "from": "Bengaluru",
                                 "to": "Bangalore"}]


def test_the_display_name_is_resolved_at_RENDER_time(client):
    import auth
    from conftest import TEST_USER

    uid = auth.find_user(TEST_USER)["id"]
    assert AD.editor_label(uid) == "Test Owner"

    # The half `reprice_log` cannot do: the account is gone and the page says so
    # rather than printing a string that identifies nobody.
    assert "deleted user" in AD.editor_label("no-such-user")
    assert AD.editor_label("") == "not signed in"


def test_the_edit_history_is_shown_on_the_address_page(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr, city="Bangalore"),
                follow_redirects=False)
    html = client.get(f"/address/view/{aid}").get_data(as_text=True)
    assert "Edit history" in html
    assert "Bengaluru" in html and "Bangalore" in html
    assert "Test Owner" in html


def test_an_edit_that_changes_nothing_writes_no_history(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr),
                follow_redirects=False)
    assert not STORE["addresses"][aid].get(AD.EDIT_LOG_FIELD), (
        "an unchanged submit invented a history entry")


def test_an_UNREFERENCED_address_is_edited_without_a_log(client):
    """The log exists because other records depend on the value. Nothing does."""
    aid = _addr("Typo Site")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr, city="Bangalore"),
                follow_redirects=False)
    assert STORE["addresses"][aid]["city"] == "Bangalore"
    assert not STORE["addresses"][aid].get(AD.EDIT_LOG_FIELD)


def test_editing_does_not_discard_the_archive_flag_or_the_history(client):
    """
    ⚠ The edit route used to be `STORE["addresses"][id] = {"id": id, **data}`,
    which threw away every key `_validate()` does not produce. Editing an
    archived address would have silently un-archived it.
    """
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr, city="Bangalore"),
                follow_redirects=False)
    after = STORE["addresses"][aid]
    assert AD.is_active(after) is False, "editing silently un-archived it"
    assert len(after[AD.EDIT_LOG_FIELD]) == 1

    client.post(f"/address/edit/{aid}", data=_edit_form(after, city="Mysuru"),
                follow_redirects=False)
    assert len(STORE["addresses"][aid][AD.EDIT_LOG_FIELD]) == 2, (
        "the second edit replaced the history instead of appending to it")


# ═══ 5. TYPE is the one locked field ═══════════════════════════════════════

def test_the_type_cannot_change_while_anything_references_it(client):
    """
    ⚠ Flip a `site` to a `vendor` and it leaves `SITE_TYPES`; the picker stops
    offering it and every existing reference dangles with nothing on screen
    explaining why.
    """
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    addr = STORE["addresses"][aid]
    resp = client.post(f"/address/edit/{aid}",
                       data=_edit_form(addr, type="vendor"))
    assert STORE["addresses"][aid]["type"] == "site", "the type lock let it through"
    html = resp.get_data(as_text=True)
    assert "type cannot be changed" in html
    assert "1 record" in html, "the refusal did not say what was blocking it"


def test_the_type_lock_does_not_block_any_other_field(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}",
                data=_edit_form(addr, label="Whitefield Phase 2", city="Mysuru"),
                follow_redirects=False)
    after = STORE["addresses"][aid]
    assert after["label"] == "Whitefield Phase 2"
    assert after["city"] == "Mysuru"


def test_the_type_of_an_unreferenced_address_changes_freely(client):
    aid = _addr("Typo Site")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr, type="vendor"),
                follow_redirects=False)
    assert STORE["addresses"][aid]["type"] == "vendor"


def test_the_edit_form_shows_the_type_read_only_when_referenced(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    html = client.get(f"/address/edit/{aid}").get_data(as_text=True)
    assert 'name="type"' in html
    assert "readonly" in html
    assert 'type="hidden" name="type"' in html, (
        "a readonly control that submits nothing lets _validate() rewrite the "
        "field the lock exists to protect")


# ═══ 6. SITE_TYPES lives in ONE place ══════════════════════════════════════

def test_site_types_is_defined_in_address_py():
    """
    ⚠ **Two pickers that can disagree about what counts as a site is the
    defect.** `project.py` and `employee.py` must read one tuple, and the one
    module they both already import is where it lives.
    """
    import ast
    tree = ast.parse((REPO / "address.py").read_text(encoding="utf8"))
    names = [t.id for n in tree.body if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)]
    assert "SITE_TYPES" in names, "SITE_TYPES is not defined in address.py"
    assert AD.SITE_TYPES == ("site", "office")


def test_employee_site_types_is_the_same_object_not_a_copy():
    assert EMP.SITE_TYPES is AD.SITE_TYPES, (
        "employee.py carries its own tuple again — two definitions can drift "
        "and a site offered by one picker and not the other is exactly that")


def test_address_py_does_not_import_the_modules_that_import_it():
    """The one-way trick. An import back from here is a cycle at boot."""
    import ast
    tree = ast.parse((REPO / "address.py").read_text(encoding="utf8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    for banned in ("project", "employee", "attendance", "po_draft",
                   "purchase", "challan", "quotation", "boq"):
        assert banned not in found, (
            f"address.py imports {banned}.py, which imports address.py — that "
            f"is a cycle at boot. Read STORE directly, as it does now")


# ═══ 7. The picker no longer seeds ═════════════════════════════════════════

def test_picker_options_does_not_seed_the_demo_book():
    """
    ⚠ **Rendering a form is not a reason to write six demo records into a
    client's database**, and this function is reached from five other modules'
    forms.
    """
    saved_book = dict(STORE["addresses"])
    saved_flag = STORE.get("_addr_seeded")
    try:
        STORE["addresses"].clear()
        STORE["_addr_seeded"] = False
        AD.picker_options()
        AD.picker_payload()
        assert STORE["addresses"] == {}, (
            "rendering a picker seeded the address book")
        assert STORE["_addr_seeded"] is False
    finally:
        STORE["addresses"].clear()
        STORE["addresses"].update(saved_book)
        STORE["_addr_seeded"] = saved_flag


def test_the_seed_still_runs_where_the_repos_other_seeds_run():
    """
    Nothing lost a seed; one form stopped causing one. `dashboard.index()` calls
    it beside `ensure_demo_products()`, and every route in `address.py` calls it.
    """
    dash = (REPO / "dashboard.py").read_text(encoding="utf8")
    assert "ensure_demo_addresses()" in dash
    addr = (REPO / "address.py").read_text(encoding="utf8")
    assert addr.count("ensure_demo_addresses()") >= 6, (
        "the address routes stopped seeding too — the book would open empty "
        "on a fresh install")


def test_has_options_answers_the_empty_book_case():
    saved_book = dict(STORE["addresses"])
    try:
        STORE["addresses"].clear()
        assert AD.has_options(AD.SITE_TYPES) is False
        _addr("Whitefield")
        assert AD.has_options(AD.SITE_TYPES) is True
        assert AD.has_options(("vendor",)) is False
    finally:
        STORE["addresses"].clear()
        STORE["addresses"].update(saved_book)


# ═══ 8. Escaping — three new sinks ═════════════════════════════════════════

PAYLOAD = '<script>alert(1)</script>'


def test_a_hostile_label_is_escaped_in_the_reference_chips(client):
    aid = _addr(PAYLOAD, aid="addr-hostile")
    _project(site_address_id=aid, site_address=PAYLOAD, name=PAYLOAD)
    for url in (f"/address/delete/{aid}", f"/address/view/{aid}",
                f"/address/edit/{aid}"):
        html = client.get(url).get_data(as_text=True)
        assert PAYLOAD not in html, f"{url} emitted a raw payload"
        assert "&lt;script&gt;" in html, f"{url} did not render it at all"


def test_a_hostile_value_is_escaped_in_the_edit_log(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    addr = STORE["addresses"][aid]
    client.post(f"/address/edit/{aid}", data=_edit_form(addr, company=PAYLOAD),
                follow_redirects=False)
    html = client.get(f"/address/view/{aid}").get_data(as_text=True)
    assert PAYLOAD not in html
    assert "&lt;script&gt;" in html


def test_the_list_page_marks_archived_and_counts_references(client):
    aid = _addr("Whitefield")
    _project(site_address_id=aid, site_address="Whitefield")
    client.post(f"/address/archive/{aid}", follow_redirects=False)
    html = client.get("/address/").get_data(as_text=True)
    assert "Archived" in html
    assert "1 ref" in html
    assert f"/address/view/{aid}" in html
