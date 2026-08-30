"""
The site is a picker over the ADDRESS BOOK — CC-2 **C4** / **C5**.

`site` was free text on the employee master and on an attendance marking until
30 August 2026, which is why the live data spells one place more than one way.
A site-wise labour cost split across two spellings is wrong in a way nobody
notices, because both halves look right.

### What this file pins, in order of how badly it would hurt to get wrong

1. ⚠ **AN EXISTING STRING IS NEVER FUZZY-MATCHED.** `Banglore` does not become
   `Bangalore`. A wrong automatic match moves labour cost to the wrong site and
   looks exactly like a right one — the same defect `po_parts.py` shipped with
   156 invented aliases, one register along (ABOUT.md §2h).
2. ⚠ **AN UNMATCHED STRING IS NEVER DROPPED.** It is left exactly as recorded,
   marked `unmapped`, and reported on both registers. A string nothing surfaces
   is a silent drop by another route: the cost is still attributed to a site
   nobody can find, and nobody is ever told.
3. **Leaving the picker alone on an unmapped record keeps the string.** Mapping
   is a deliberate act, exactly as re-entering a day rate is.
4. **A dangling id is refused**, not stored. A link to an address that does not
   exist reads on every page as a mapped record and is not one.
5. **The picker offers sites and offices only** — a vendor is somebody we buy
   from, not a place somebody worked a shift.
6. ⚠ **The new sinks are escaped**, and `tests/test_escaping.py` cannot cover
   them: its `POISONED_COLLECTIONS` deliberately excludes `employees` and
   `attendance`, because `test_hardening.py` asserts nothing seeds either and a
   fixture row would read to it exactly like a seeder. §5 of this file is the
   substitute.

⚠ **Do not weaken any of these to make a red suite green.** If (1) fails,
somebody's wages are being counted against a site they never worked on.
"""

import pathlib

import pytest

import employee as EMP
from store import STORE

REPO = pathlib.Path(__file__).resolve().parent.parent

DAY = "2026-08-29"

# Ids minted by `_addr()`, so `_clean()` can take them back out of the shared
# address book — `tests/test_challan.py` reads `next(iter(...))` out of it.
_MINTED = set()


@pytest.fixture(autouse=True)
def _clean():
    for key in ("employees", "attendance"):
        STORE.setdefault(key, {}).clear()
    _MINTED.clear()
    yield
    for key in ("employees", "attendance"):
        STORE.setdefault(key, {}).clear()
    for aid in _MINTED:
        STORE.setdefault("addresses", {}).pop(aid, None)
    _MINTED.clear()


def _addr(label, atype="site", aid=None):
    aid = aid or f"addr-{label.lower().replace(' ', '-')}"
    _MINTED.add(aid)
    STORE.setdefault("addresses", {})[aid] = {
        "id": aid, "label": label, "type": atype,
        "contact_name": "", "company": "", "line1": "1 Site Road",
        "line2": "", "landmark": "", "city": "Bengaluru",
        "state": "Karnataka", "pincode": "560066", "country": "India",
        "phone": "", "email": "", "gstin": "",
    }
    return aid


def _legacy_employee(eid="old-1", site="Banglore", **over):
    """An employee as the register wrote them when `site` was free text."""
    rec = {"id": eid, "name": "Ramesh Patil", "code": "SF-014",
           "designation": "Fitter", "site": site, "date_joined": "2026-04-01",
           "day_rate": 1000.0, "active": True, "notes": "",
           "created_at": "2026-08-29 10:00", "updated_at": "2026-08-29 10:00"}
    rec.update(over)
    STORE["employees"][eid] = rec
    return rec


def _legacy_marking(rid="am-1", site="Banglore", **over):
    rec = {"id": rid, "date": DAY, "employee_id": "old-1",
           "employee_name": "Ramesh Patil", "employee_code": "SF-014",
           "day_rate": 1000.0, "site": site, "status": "present",
           "ot_hours": 2.0, "notes": "",
           "created_at": "2026-08-29 10:05", "updated_at": "2026-08-29 10:05"}
    rec.update(over)
    STORE["attendance"][rid] = rec
    return rec


def _run_migration():
    """What `tools/backfill_site_links.py --write` does, in-process."""
    index = {str(a.get("label") or "").strip(): aid
             for aid, a in (STORE.get("addresses") or {}).items()
             if str(a.get("label") or "").strip()}
    for coll in ("employees", "attendance"):
        for r in (STORE.get(coll) or {}).values():
            if EMP.SITE_SOURCE_FIELD in r:
                continue
            site = str(r.get("site") or "").strip()
            if not site:
                continue
            aid = index.get(site)
            if aid:
                r[EMP.SITE_ADDRESS_FIELD] = aid
                r[EMP.SITE_SOURCE_FIELD] = EMP.SITE_BOOK
            else:
                r[EMP.SITE_ADDRESS_FIELD] = ""
                r[EMP.SITE_SOURCE_FIELD] = EMP.SITE_UNMAPPED
    return index


# ═══ 1. ⚠ NOTHING IS FUZZY-MATCHED ═════════════════════════════════════════

@pytest.mark.parametrize("stored,book", [
    ("Banglore",         "Bangalore"),          # the live misspelling
    ("bangalore",        "Bangalore"),          # case
    ("Bangalore ",       "Bangalore"),          # already handled by strip()
    ("Bangalore, KA",    "Bangalore"),          # a suffix
    ("Sify Bangalore",   "Bangalore"),          # a prefix
    ("Bangalore  Site",  "Bangalore Site"),     # collapsed whitespace
])
def test_a_near_miss_is_never_matched_automatically(stored, book):
    """
    ⚠ **THE TEST THIS WHOLE MIGRATION EXISTS TO BE SAFE UNDER.** Every row is a
    string a less careful matcher would happily link. Not one of them may be.

    The one exception is `strip()`, which is not a fuzzy match — trailing
    whitespace is not a different place, and `"Bangalore "` and `"Bangalore"`
    are one string typed twice. The third row asserts it links, and it is in
    this list rather than a separate one so the boundary is visible.
    """
    _addr(book)
    e = _legacy_employee(site=stored)
    _run_migration()

    if stored.strip() == book:
        assert not EMP.is_unmapped_site(e), (
            "trailing whitespace is not a different site — strip() is the one "
            "normalisation this migration performs, and it is not fuzzy")
        return

    assert EMP.is_unmapped_site(e), (
        f"{stored!r} was matched to the address {book!r}. A wrong automatic "
        f"match moves labour cost to the wrong site and looks exactly like a "
        f"right one.")
    assert e[EMP.SITE_ADDRESS_FIELD] == "", "a near miss was given a link"


def test_an_exact_match_IS_linked():
    """
    The control on the test above. A guard that matches nothing is not a
    matcher, and this proves the migration can actually link.
    """
    aid = _addr("Whitefield")
    e = _legacy_employee(site="Whitefield")
    _run_migration()

    assert not EMP.is_unmapped_site(e)
    assert e[EMP.SITE_ADDRESS_FIELD] == aid
    assert e[EMP.SITE_SOURCE_FIELD] == EMP.SITE_BOOK
    assert e["site"] == "Whitefield", "the label is not rewritten by a link"


def test_the_migration_never_touches_the_stored_string():
    """
    ⚠ **Left exactly as recorded.** `Banglore` stays `Banglore`. It is the
    evidence of where somebody worked and the only thing a human has to go on
    when they map it.
    """
    _addr("Bangalore")
    e = _legacy_employee(site="Banglore")
    m = _legacy_marking(site="Banglore")
    _run_migration()

    assert e["site"] == "Banglore"
    assert m["site"] == "Banglore"


def test_the_migration_is_idempotent():
    """A record already classified is not reclassified — mapping one by hand
    afterwards must not be undone by a second run."""
    aid = _addr("Whitefield")
    e = _legacy_employee(site="Banglore")
    _run_migration()
    assert EMP.is_unmapped_site(e)

    # A human maps it.
    e[EMP.SITE_ADDRESS_FIELD] = aid
    e[EMP.SITE_SOURCE_FIELD] = EMP.SITE_BOOK
    e["site"] = "Whitefield"

    _run_migration()
    assert e[EMP.SITE_ADDRESS_FIELD] == aid, "a second run undid a human's work"
    assert not EMP.is_unmapped_site(e)


def test_a_blank_site_is_not_marked_at_all():
    """No site was recorded, so there is nothing to map and nothing to report.
    Marking it would put a record on the unmapped list that nobody can act on."""
    e = _legacy_employee(site="")
    _run_migration()
    assert not EMP.is_unmapped_site(e)
    assert EMP.SITE_SOURCE_FIELD not in e or not e[EMP.SITE_SOURCE_FIELD]


# ═══ 2. ⚠ AN UNMAPPED STRING IS REPORTED, NOT DROPPED ══════════════════════

def test_the_report_names_every_unmapped_string_and_counts_them():
    _addr("Whitefield")
    _legacy_employee(eid="e1", site="Banglore")
    _legacy_employee(eid="e2", site="Banglore", code="SF-015")
    _legacy_employee(eid="e3", site="Whitefield", code="SF-016")
    _legacy_marking(rid="m1", site="Banglore")
    _run_migration()

    by_emp = EMP.unmapped_sites_in(STORE["employees"])
    by_att = EMP.unmapped_sites_in(STORE["attendance"])
    assert sorted(by_emp) == ["Banglore"]
    assert sorted(by_emp["Banglore"]) == ["e1", "e2"]
    assert by_att == {"Banglore": ["m1"]}


def test_the_report_can_actually_see_an_unmapped_record():
    """
    ⚠ **The vacuity check.** A report that returns `{}` passes whether it is
    looking or not. This asserts the empty answer is empty for the right reason
    by planting one record and watching it appear.
    """
    _addr("Whitefield")
    e = _legacy_employee(site="Whitefield")
    _run_migration()
    assert EMP.unmapped_sites_in(STORE["employees"]) == {}, (
        "the report claims an unmapped record where the site matched exactly")

    _legacy_employee(eid="e2", site="Banglore", code="SF-015")
    _run_migration()
    assert EMP.unmapped_sites_in(STORE["employees"]) == {"Banglore": ["e2"]}, (
        "the report cannot see an unmapped record, so its empty answer above "
        "means nothing")


def test_the_mark_is_never_inferred_from_a_missing_link():
    """
    `is_unmapped_site()` reads the explicit field and nothing else —
    `is_pre_day_rate()`'s argument, and for the same reason. A record written
    through the picker today either carries a link or carries no site at all, so
    an inferred mark could only ever be a guess about a record that predates the
    picker.
    """
    e = _legacy_employee(site="Banglore")
    assert not EMP.is_unmapped_site(e), (
        "a record with a site and no link reads as unmapped before the "
        "migration has classified it — the mark is inferred, and it will grow")
    _run_migration()
    assert EMP.is_unmapped_site(e)


def test_both_registers_report_the_unmapped_string(client):
    """
    End to end. A report that exists only in a tool nobody runs is not a report.
    """
    _addr("Whitefield")
    _legacy_employee(site="Banglore")
    _legacy_marking(site="Banglore")
    _run_migration()

    emp_page = client.get("/employee/").get_data(as_text=True)
    assert "not in the address book" in emp_page
    assert "Banglore" in emp_page

    att_page = client.get(f"/attendance/?date={DAY}").get_data(as_text=True)
    assert "not in the address book" in att_page
    assert "Banglore" in att_page
    assert "SITE NOT MAPPED" in att_page, "the row itself must carry the chip"


def test_a_mapped_record_carries_no_band_or_chip(client):
    """The other half: the marker appears only where the mark is."""
    _addr("Whitefield")
    _legacy_employee(site="Whitefield")
    _legacy_marking(site="Whitefield")
    _run_migration()

    for page in (client.get("/employee/").get_data(as_text=True),
                 client.get(f"/attendance/?date={DAY}").get_data(as_text=True)):
        assert "not in the address book" not in page
        assert "SITE NOT MAPPED" not in page


# ═══ 3. THE PICKER ITSELF ══════════════════════════════════════════════════

def test_the_picker_offers_sites_and_offices_and_not_vendors(client):
    """
    ⚠ **Offering a vendor as a place somebody worked would put labour cost
    against a supplier.** The narrowing is ours — CC-2 says nothing — and it is
    one tuple to widen.
    """
    _addr("A Real Site", "site")
    _addr("The Office", "office")
    _addr("A Supplier", "vendor")
    _addr("Somewhere We Ship", "shipping")

    html = EMP.site_options()
    assert "A Real Site" in html
    assert "The Office" in html
    assert "A Supplier" not in html, "a vendor was offered as a site"
    assert "Somewhere We Ship" not in html


def test_the_employee_form_posts_a_picker_and_not_a_text_box(client):
    html = client.get("/employee/new").get_data(as_text=True)
    assert 'name="site_id"' in html
    assert '<select id="site_id"' in html
    assert 'name="site"' not in html, (
        "the free-text site box is still on the form — free text is the defect "
        "this change removes")


def test_the_attendance_form_posts_a_picker_and_not_a_text_box(client):
    html = client.get("/attendance/mark").get_data(as_text=True)
    assert 'name="site_id"' in html
    assert 'name="site" ' not in html and 'name="site"/' not in html


def test_choosing_an_address_stores_the_link_and_snapshots_the_label(client):
    """
    ⚠ **Three keys, and the label is a SNAPSHOT.** Renaming an address next
    March must not restate which site somebody worked on last August — the
    freeze contract `challan.py` holds for its consignee and `ra.py` for its
    party block.
    """
    aid = _addr("Whitefield")
    r = client.post("/employee/new", data={
        "name": "Someone", "code": "SF-500", "day_rate": "900",
        "site_id": aid, "active": "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]

    e = list(STORE["employees"].values())[-1]
    assert e["site"] == "Whitefield"
    assert e[EMP.SITE_ADDRESS_FIELD] == aid
    assert e[EMP.SITE_SOURCE_FIELD] == EMP.SITE_BOOK

    STORE["addresses"][aid]["label"] = "Renamed Entirely"
    assert STORE["employees"][e["id"]]["site"] == "Whitefield", (
        "renaming the address rewrote a record of where somebody worked")


def test_a_dangling_address_id_is_REFUSED(client):
    """
    ⚠ **Refused, not stored blank.** A link to an address that does not exist
    reads on every page as a mapped record and is not one — which is worse than
    an unmapped string, because nothing reports it.
    """
    r = client.post("/employee/new", data={
        "name": "Someone", "code": "SF-501", "day_rate": "900",
        "site_id": "no-such-address", "active": "1"})
    assert r.status_code == 200, "a dangling id was accepted"
    assert "not in the address book any more" in r.get_data(as_text=True)
    assert not STORE["employees"], "nothing may be written on a refused POST"


def test_a_blank_picker_on_an_unmapped_record_KEEPS_the_string(client):
    """
    ⚠ **THE ONE THAT MATTERS MOST ON THE EDIT FORM.** Leaving the picker alone
    on a record carrying `Banglore` must not silently delete `Banglore`. The
    string is the evidence of where somebody worked, and the rule for this whole
    migration is that an unmapped string is left, marked and reported — not
    dropped by whoever next opens the record to fix a typo in the name.
    """
    _addr("Whitefield")
    e = _legacy_employee(site="Banglore")
    _run_migration()
    assert EMP.is_unmapped_site(e)

    r = client.post("/employee/edit/old-1", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "1000",
        "site_id": "", "active": "1"})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]

    e = STORE["employees"]["old-1"]
    assert e["site"] == "Banglore", "an unmapped site string was dropped"
    assert EMP.is_unmapped_site(e), "and its mark went with it"


def test_a_blank_picker_on_an_ORDINARY_record_clears_the_site(client):
    """
    The control on the test above. On a record whose site is a real link, a
    blank picker means "no site", which is a state the register already renders
    ("no site named") and C4 already permits.
    """
    aid = _addr("Whitefield")
    e = _legacy_employee(site="Whitefield")
    _run_migration()
    assert e[EMP.SITE_ADDRESS_FIELD] == aid

    r = client.post("/employee/edit/old-1", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "1000",
        "site_id": "", "active": "1"})
    assert r.status_code == 302

    e = STORE["employees"]["old-1"]
    assert e["site"] == ""
    assert e[EMP.SITE_ADDRESS_FIELD] == ""
    assert e[EMP.SITE_SOURCE_FIELD] == ""


def test_mapping_an_unmapped_record_clears_the_mark(client):
    """The way out of the unmapped set, and the only way: a person chooses."""
    aid = _addr("Whitefield")
    e = _legacy_employee(site="Banglore")
    _run_migration()

    r = client.post("/employee/edit/old-1", data={
        "name": "Ramesh Patil", "code": "SF-014", "day_rate": "1000",
        "site_id": aid, "active": "1"})
    assert r.status_code == 302

    e = STORE["employees"]["old-1"]
    assert e["site"] == "Whitefield"
    assert e[EMP.SITE_ADDRESS_FIELD] == aid
    assert not EMP.is_unmapped_site(e)


def test_the_attendance_form_prefills_the_employees_own_site(client):
    """
    The common case stays one selection. It prefills the LINK, because a picker
    needs an option value to select.
    """
    aid = _addr("Whitefield")
    r = client.post("/employee/new", data={
        "name": "Someone", "code": "SF-502", "day_rate": "900",
        "site_id": aid, "active": "1"})
    assert r.status_code == 302
    eid = list(STORE["employees"])[-1]

    html = client.get("/attendance/mark").get_data(as_text=True)
    assert f'value="{aid}"' in html, "the option is not even on the form"

    # The prefill fires once an employee is chosen, which the form does through
    # `_site_of()`; assert the accessor rather than the browser's behaviour.
    import attendance as AT
    assert AT._site_of(eid) == aid


def test_an_employee_whose_own_site_is_unmapped_prefills_nothing(client):
    """
    There is no option to select, so the picker opens blank rather than guessing
    — which is the honest state.
    """
    _addr("Whitefield")
    _legacy_employee(site="Banglore")
    _run_migration()

    import attendance as AT
    assert AT._site_of("old-1") == ""


# ═══ 5. ⚠ THE NEW SINKS ARE ESCAPED, AND THE SWEEP CANNOT COVER THEM ═══════

PAYLOAD = "<script>alert(1)</script>"


def test_an_unmapped_site_string_is_escaped_everywhere_it_renders(client):
    """
    ⚠ **`tests/test_escaping.py` CANNOT cover this, and that is why the test is
    here.** Its `POISONED_COLLECTIONS` deliberately excludes `employees` and
    `attendance` — `test_hardening.py` asserts that nothing seeds either, so a
    fixture row written by that sweep would read exactly like a seeder to it.
    The unmapped-site band and chip are therefore **new sinks the standing sweep
    is blind to**, and they render a string that was free text somebody typed.

    ABOUT.md §9: escape at the interpolation site, never a response filter.
    """
    _addr("Whitefield")
    _legacy_employee(site=PAYLOAD)
    _legacy_marking(site=PAYLOAD)
    _run_migration()

    for url in ("/employee/", "/employee/view/old-1", "/employee/edit/old-1",
                f"/attendance/?date={DAY}", "/attendance/edit/am-1",
                "/attendance/delete/am-1"):
        html = client.get(url).get_data(as_text=True)
        assert html, f"{url} did not render"
        assert PAYLOAD not in html, f"{url} emitted the payload raw"
        assert "&lt;script&gt;" in html, (
            f"{url} did not render the site string at all — the assertion "
            f"above passes for the wrong reason")


def test_an_address_LABEL_is_escaped_in_the_picker(client):
    """
    The other half of the same surface: an address label is typed by a user at
    `/address/add`, and it now reaches two more forms through `site_options()`.
    """
    _addr(PAYLOAD)
    for url in ("/employee/new", "/attendance/mark"):
        html = client.get(url).get_data(as_text=True)
        assert PAYLOAD not in html, f"{url} emitted a raw address label"
        assert "&lt;script&gt;" in html, f"{url} did not render the label"


# ═══ 4. THE SHORTFALL THIS DELIBERATELY DOES NOT CLOSE ═════════════════════

# ⚠ **REWRITTEN on 30 August 2026 (fourth pass). The join now EXISTS.** The test
# that pinned its ABSENCE is kept here VERBATIM rather than deleted — a comment
# block rather than a quote inside the new docstring, because it carries its own
# triple quotes. Nothing in it is reworded, and its first assertion is still LIVE
# below because the direction of the arrow still matters:
#
# def test_an_address_does_not_join_to_a_project():
#     """
#     ⚠ **Recorded rather than solved, because it belongs to C6, which is
#     BLOCKED.** Site-wise labour cost cannot roll up to a project: an `addresses`
#     record carries no project key, and `projects` carries a free-text
#     `site_address` string rather than an address id. This test is the evidence
#     for the note in ABOUT.md, and it fails the day somebody adds the join — at
#     which point the note is what needs rewriting, not this.
#     """
#     aid = _addr("Whitefield")
#     a = STORE["addresses"][aid]
#     assert not any(k.startswith("project") for k in a), (
#         "an address now carries a project key — the C6 shortfall recorded in "
#         "ABOUT.md has changed and the note must be rewritten")
#
#     STORE.setdefault("projects", {})["p-1"] = {
#         "id": "p-1", "name": "A Project", "norm_name": "a project",
#         "client": "", "site_address": "Whitefield, Karnataka", "notes": "",
#         "created_at": "", "updated_at": ""}
#     p = STORE["projects"]["p-1"]
#     assert isinstance(p["site_address"], str)
#     assert p["site_address"] != aid, (
#         "a project now names an address by id — the join exists and the C6 "
#         "shortfall note is out of date")
#     STORE["projects"].pop("p-1", None)
#
# ── and this is what replaces it ────────────────────────────────────────────


def test_an_address_joins_to_a_project_THROUGH_THE_PROJECT():
    """
    The join runs FROM the project, and this pins its direction and its shape.

    ⚠ **Note what did NOT happen.** It was built as `projects.site_address_id`,
    **not** as an `address.project_id`. ABOUT.md §4 named three ways out and
    called `address.project_id` the wrong shape — *"one site can carry work for
    more than one project"* — and the live data proves it, with two projects on
    one string. What was built is the **second** way out, narrowed from a list
    to a single id because the client has said *one project = one site*. The old
    test's first assertion is what holds that, and it is kept unchanged below.

    ⚠ **`site_address` is still a string and still renders.** It is the label
    SNAPSHOT now rather than free text, which is what makes every existing
    reader unchanged and existing records unharmed **by construction** rather
    than by migration.

    ⚠ **This does NOT unblock C6.** C6 is BLOCKED on CC-2's Open question 4 —
    whether attendance wages or the BOQ installation base rate is authoritative
    for labour cost — and nothing here answers it. One of the two shortfalls is
    closed; the other is untouched.
    """
    import project as PJ

    aid = _addr("Whitefield")
    a = STORE["addresses"][aid]
    # ⚠ Unchanged from the old test and still load-bearing: an address carrying
    #   a project key is the shape §4 rejects.
    assert not any(k.startswith("project") for k in a), (
        "an address now carries a project key — that is the shape ABOUT.md §4 "
        "calls wrong, because one site can carry work for more than one project")

    STORE.setdefault("projects", {})["p-1"] = {
        "id": "p-1", "name": "A Project", "norm_name": "a project",
        "client": "", "site_address": "Whitefield", "site_address_id": aid,
        "notes": "", "created_at": "", "updated_at": ""}
    p = STORE["projects"]["p-1"]
    try:
        assert p[PJ.SITE_ADDRESS_ID_FIELD] == aid, "the join does not resolve"
        assert isinstance(p["site_address"], str), (
            "site_address stopped being a string — every existing reader "
            "renders it and none of them changed")
        assert p["site_address"] != aid, (
            "site_address holds the id — it is the label SNAPSHOT, and a "
            "register printing a UUID is what that mistake looks like")
        assert PJ.site_label_of(aid) == "Whitefield"
        assert PJ.site_drift(p) is None
        assert PJ.is_legacy_site(p) is False
    finally:
        STORE["projects"].pop("p-1", None)


def test_a_project_written_before_the_picker_is_LEGACY_and_is_not_rewritten():
    """
    The other half of the same shape: a string with no id joins to nothing, says
    so, and is left exactly as it stands. `Banglore` stays `Banglore`.
    """
    import project as PJ

    _addr("Bangalore, Karnataka")
    STORE.setdefault("projects", {})["p-2"] = {
        "id": "p-2", "name": "Legacy", "norm_name": "legacy",
        "client": "", "site_address": "Banglore, Karnataka",
        "notes": "", "created_at": "", "updated_at": ""}
    p = STORE["projects"]["p-2"]
    try:
        assert PJ.is_legacy_site(p) is True
        assert PJ.site_drift(p) is None, (
            "a record with no id has nothing to compare against; reporting "
            "drift on it would name a disagreement that does not exist")
        assert p["site_address"] == "Banglore, Karnataka", (
            "the legacy string was rewritten — a wrong automatic match puts a "
            "project on the wrong site and looks exactly like a right one")
    finally:
        STORE["projects"].pop("p-2", None)


def test_employee_py_still_does_not_import_project():
    """
    The prohibition `test_import_directions.py` holds, restated here because the
    site picker is exactly the change that would have been tempted to break it.
    """
    import ast
    tree = ast.parse((REPO / "employee.py").read_text(encoding="utf8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            assert "project" not in [mod] + names, (
                "employee.py imports project.py — linking a person to a "
                "project is C6, which is BLOCKED")
