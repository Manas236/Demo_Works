"""
The duplicate guard and merge-then-delete (6 November 2026).

CLIENT_CHANGES.md §0, the **seventieth** block. On the live database the client
created NEWAGE FIRE FIGHTING CO. LIMITED (GSTIN 24AABCN5691G1ZF) twice, once as
an office and once as a vendor, and nothing stopped it. Both cards then read
"2 refs" because `references_of()` counted snapshot NAME matches as well as ID
links. This file pins the three things that pass built:

1. ⚠ **THE DUPLICATE GUARD IS ONE FUNCTION**, `address.duplicate_guard()`,
   called by `create_record()` and `update_record()` — the Add form, the edit
   form, a save carrying a GSTIN auto-fill, and Import from Excel all meet it.
   EXACT duplicate (same GSTIN + PIN + line 1; or, where either side lacks a
   GSTIN, the same company + PIN + line 1), across every type, active or
   archived: refused, no override. Same GSTIN at a different address: the
   "different branch" tick is required.
2. **Only ID links count.** A name-only mention never blocks a plain delete and
   is listed as "mentions this name, not linked, not affected".
3. ⚠ **MERGE-THEN-DELETE CHANGES THE ID FIELD AND NOTHING ELSE.** The
   replacement must be active, not itself, and a type every link's own picker
   offers. The print of every document carrying an address id is byte for byte
   the same after a merge. A merge that half-persisted can be run again and
   finishes with no double effect.

⚠ Do not weaken any of these to make a red suite green.
"""

import copy

import pytest

import address as AD
import auth
import challan
import docimport as DI
import employee as EMP
import po_draft
import purchase
import workorder
from store import STORE

from test_print_golden import (  # noqa: F401
    GOLD_DC, GOLD_DPO, GOLD_PO, golden, golden_dc, golden_dpo, pinned_identity)
from test_work_orders import GOLD_WO, golden_wo  # noqa: F401

NEWAGE_GSTIN = "24AABCN5691G1ZF"   # the live pair's GSTIN; it passes its check character

_TOUCHED = ("projects", "employees", "attendance", "purchase_orders",
            "purchases", "delivery_challans", "work_orders")
_MINTED = set()


@pytest.fixture(autouse=True)
def _clean():
    # The WHOLE book and its seed flag are restored, not just the rows this
    # file added: a page rendered here can run the demo seeder, and removing
    # those rows while `_addr_seeded` stays True empties the book for every
    # later file (found by running this file before test_entity_fallbacks).
    saved = {k: dict(STORE.setdefault(k, {})) for k in _TOUCHED}
    book = copy.deepcopy(STORE.setdefault("addresses", {}))
    seeded = STORE.get("_addr_seeded")
    for k in _TOUCHED:
        STORE[k].clear()
    STORE.setdefault("gst_cache", {}).pop(NEWAGE_GSTIN, None)
    AD.ensure_demo_addresses()     # seeded now, so no request seeds mid-test
    yield
    for k in _TOUCHED:
        STORE[k].clear()
        STORE[k].update(saved[k])
    STORE["addresses"].clear()
    STORE["addresses"].update(book)
    STORE["_addr_seeded"] = seeded
    _MINTED.clear()
    STORE["gst_cache"].pop(NEWAGE_GSTIN, None)


def _addr(aid, label, atype="office", **over):
    _MINTED.add(aid)
    rec = {"id": aid, "label": label, "type": atype, "contact_name": "",
           "company": "", "line1": "1 Site Road", "line2": "", "landmark": "",
           "city": "Ahmedabad", "state": "Gujarat", "pincode": "382213",
           "country": "India", "phone": "", "email": "", "gstin": ""}
    rec.update(over)
    STORE["addresses"][aid] = rec
    return aid


def _form(**over):
    f = {"label": "NEWAGE Office", "type": "office", "contact_name": "",
         "company": "NEWAGE FIRE FIGHTING CO. LIMITED",
         "line1": "Plot 12, GIDC Estate", "line2": "Naroda", "landmark": "",
         "city": "Ahmedabad", "state": "Gujarat", "pincode": "382330",
         "phone": "", "email": "", "gstin": NEWAGE_GSTIN}
    f.update(over)
    return f


def _book_ids():
    return set(STORE["addresses"])


def _as(client, user):
    with client.session_transaction() as sess:
        sess[auth.SESSION_KEY] = user["id"]


def _user(client, name, role, **over):
    auth.ensure_builtin_roles()
    old = auth.find_user(name)
    if old:
        del STORE["users"][old["id"]]
    u = auth.create_user(name, name.title(), f"{name}-password-long", [role],
                         created_by="test")
    u.update(over)
    _as(client, u)
    return u


# ═══ 1. Normalisation and the rule itself ═══════════════════════════════════

def test_the_key_normalises_gstin_pin_line1_and_company():
    k = AD.duplicate_key({"gstin": " 24aabcn 5691g1zf ", "pincode": "382 330",
                          "line1": "  Plot 12,  GIDC-Estate. ",
                          "company": "NEWAGE Fire_Fighting Co. LIMITED"})
    assert k == {"gstin": "24AABCN5691G1ZF", "pincode": "382330",
                 "line1": "plot 12 gidc estate",
                 "company": "newage fire fighting co limited"}


def test_a_blank_key_matches_nothing():
    """`tools/backfill_project_sites.py` wrote site addresses blank but for the
    label; they must not all be one another's duplicate."""
    _addr("a-blank-1", "Site One", "site", line1="", pincode="", company="")
    assert AD.duplicates_of({"label": "Site Two", "line1": "", "pincode": "",
                             "company": ""}) == ([], [])
    _addr("a-noco", "No company", line1="9 Road", pincode="400001", company="")
    exact, _ = AD.duplicates_of({"line1": "9 Road", "pincode": "400001", "company": ""})
    assert exact == [], "two records with no company matched on the company rule"


def test_either_side_without_a_gstin_falls_back_to_the_company():
    _addr("a-g", "With GSTIN", company="Acme Ltd", line1="5 Road",
          pincode="400001", gstin=NEWAGE_GSTIN)
    exact, _ = AD.duplicates_of({"company": "ACME LTD.", "line1": "5, road",
                                 "pincode": "400001", "gstin": ""})
    assert [a["id"] for a in exact] == ["a-g"]


def test_two_different_gstins_at_one_address_are_not_duplicates():
    """Two companies in one building. The rule is GSTIN-first."""
    _addr("a-g1", "Tenant A", company="Acme", line1="5 Road", pincode="400001",
          gstin=NEWAGE_GSTIN)
    exact, same = AD.duplicates_of({"company": "Acme", "line1": "5 Road",
                                    "pincode": "400001", "gstin": "29ZZZZZ9999Z1Z9"})
    assert exact == [] and same == []


# ═══ 2. CREATE: the form, the auto-fill save, the import, the function ══════

def test_the_live_office_vs_vendor_pair_is_refused(client):
    r = client.post("/address/add", data=_form(), follow_redirects=False)
    assert r.status_code == 302
    office = next(a for a in STORE["addresses"].values()
                  if a.get("gstin") == NEWAGE_GSTIN)
    before = _book_ids()
    html = client.post("/address/add",
                       data=_form(label="NEWAGE Vendor", type="vendor")).get_data(as_text=True)
    assert _book_ids() == before, "the vendor duplicate of the office was saved"
    assert "already in the book" in html
    assert f"/address/view/{office['id']}" in html, "the refusal does not link the record"
    assert "Office" in html, "the refusal does not name the existing record's type"
    assert 'value="NEWAGE Vendor"' in html, "the typed form was not kept"


def test_an_exact_duplicate_without_any_gstin_is_refused(client):
    _addr("a-co", "Acme", company="Acme Fire Ltd", line1="5 Road", pincode="400001",
          city="Mumbai", state="Maharashtra")
    before = _book_ids()
    client.post("/address/add", data=_form(
        label="Acme again", gstin="", company="ACME FIRE LTD.", line1="5,  road",
        pincode="400001", city="Mumbai", state="Maharashtra"))
    assert _book_ids() == before


def test_the_refusal_offers_unarchive_for_an_archived_match(client):
    _addr("a-arch", "Old NEWAGE", "vendor", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN, active=False)
    before = _book_ids()
    html = client.post("/address/add", data=_form()).get_data(as_text=True)
    assert _book_ids() == before, "an ARCHIVED match was not counted"
    assert "archived" in html
    assert "/address/unarchive/a-arch" in html, "no un-archive was offered"


def test_the_exact_refusal_has_no_override(client):
    """Ticking the branch box does not get an exact duplicate through."""
    _addr("a-x", "NEWAGE", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    before = _book_ids()
    client.post("/address/add", data=_form(branch_ok="1"))
    assert _book_ids() == before


def test_same_gstin_at_a_different_address_needs_the_branch_tick(client):
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    before = _book_ids()
    form = _form(label="NEWAGE Vapi", line1="Shed 4, Vapi GIDC", pincode="396195",
                 city="Vapi")
    html = client.post("/address/add", data=form).get_data(as_text=True)
    assert _book_ids() == before, "a same-GSTIN branch was saved without the tick"
    assert 'name="branch_ok"' in html and "required" in html
    assert "This is a different branch of the same company" in html
    assert "/address/view/a-hq" in html, "the matches were not listed"
    assert 'value="Shed 4, Vapi GIDC"' in html, "the typed form was not kept"
    client.post("/address/add", data=dict(form, branch_ok="1"))
    assert len(_book_ids() - before) == 1, "the ticked branch was not saved"


def test_a_save_carrying_a_gstin_auto_fill_meets_the_guard(client):
    """The auto-fill only fills the form; its save is the ordinary one, with a
    fresh cache entry stamping `gst_status`. That save is refused too."""
    import time
    _addr("a-hq", "NEWAGE HQ", "office", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    STORE["gst_cache"][NEWAGE_GSTIN] = {
        "id": NEWAGE_GSTIN, "gstin": NEWAGE_GSTIN, "fetched_at": "2026-11-06 10:00",
        "fetched_ts": time.time(), "source": "GST portal",
        "result": {"gstin": NEWAGE_GSTIN, "legal_name": "NEWAGE FIRE FIGHTING CO. LIMITED",
                   "status": "Active", "active": True, "cancelled": False,
                   "fetched_at": "2026-11-06 10:00", "source": "GST portal"}}
    before = _book_ids()
    client.post("/address/add", data=_form(type="vendor", label="NEWAGE (auto-filled)"))
    assert _book_ids() == before


def test_create_record_itself_refuses_both_kinds():
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    with pytest.raises(AD.DuplicateAddress) as exc:
        AD.create_record(dict(_form(), country="India"))
    assert exc.value.kind == "exact"
    with pytest.raises(AD.DuplicateAddress) as exc:
        AD.create_record(dict(_form(line1="Elsewhere 9", pincode="396195"), country="India"))
    assert exc.value.kind == "branch"
    aid = AD.create_record(dict(_form(line1="Elsewhere 9", pincode="396195"),
                                country="India"), branch_ok=True)
    _MINTED.add(aid)


def _import_build(rows):
    """Run the Import-from-Excel address rows through the kind's own build."""
    def cells(d):
        return {k: (v, "") for k, v in d.items()}
    return DI.AddressKind().build(
        [{"row": i + 2, "cells": cells(r)} for i, r in enumerate(rows)], {"options": {}})


def _row(**over):
    r = {k: v for k, v in _form().items()}
    r.update(over)
    return r


def test_the_excel_import_refuses_an_exact_duplicate_of_the_book():
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    built = _import_build([_row(label="NEWAGE import", type="Vendor")])
    assert built["items"][0]["error"], "an imported exact duplicate was let through"
    assert "already in the address book" in built["items"][0]["error"]


def test_the_excel_import_refuses_a_duplicate_within_the_same_file():
    built = _import_build([_row(label="First"), _row(label="Second", type="Vendor")])
    assert not built["items"][0]["error"]
    assert built["items"][1]["error"] and "row 2" in built["items"][1]["error"]


def test_the_excel_import_refuses_a_same_gstin_branch_there_is_no_tick():
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    built = _import_build([_row(label="Vapi", line1="Shed 4", pincode="396195")])
    assert "different branch" in built["items"][0]["error"]


# ═══ 3. EDIT: the same rules, excluding the record itself ═══════════════════

def _edit_form(addr, **over):
    f = {k: addr.get(k, "") for k in ("label", "type", "contact_name", "company",
                                      "line1", "line2", "landmark", "city", "state",
                                      "pincode", "phone", "email", "gstin")}
    f.update(over)
    return f


def test_an_edit_that_would_make_an_exact_duplicate_is_refused(client):
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    _addr("a-other", "Other", "vendor", company="Other Co", line1="9 Lane", pincode="380001")
    before = copy.deepcopy(STORE["addresses"]["a-other"])
    html = client.post("/address/edit/a-other", data=_edit_form(
        before, company="NEWAGE", line1="Plot 12, GIDC Estate", pincode="382330",
        gstin=NEWAGE_GSTIN)).get_data(as_text=True)
    assert STORE["addresses"]["a-other"] == before
    assert "already in the book" in html


def test_an_edit_saving_the_record_as_it_is_does_not_match_itself(client):
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    addr = STORE["addresses"]["a-hq"]
    client.post("/address/edit/a-hq", data=_edit_form(addr, line1="Plot 12 GIDC Estate"))
    assert STORE["addresses"]["a-hq"]["line1"] == "Plot 12 GIDC Estate"


def test_an_edit_into_a_same_gstin_branch_needs_the_tick(client):
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    _addr("a-v", "Vapi", company="NEWAGE", line1="Shed 4", pincode="396195", city="Vapi")
    addr = STORE["addresses"]["a-v"]
    html = client.post("/address/edit/a-v",
                       data=_edit_form(addr, gstin=NEWAGE_GSTIN)).get_data(as_text=True)
    assert STORE["addresses"]["a-v"]["gstin"] == ""
    assert 'name="branch_ok"' in html
    client.post("/address/edit/a-v", data=_edit_form(addr, gstin=NEWAGE_GSTIN, branch_ok="1"))
    assert STORE["addresses"]["a-v"]["gstin"] == NEWAGE_GSTIN


def test_a_pre_existing_duplicate_pair_can_still_have_its_phone_fixed(client):
    """Judgement call recorded in ABOUT.md: an edit moving none of the four key
    fields is not checked, so the live pair stays editable until merged."""
    for aid, t in (("a-o", "office"), ("a-v", "vendor")):
        _addr(aid, f"NEWAGE {t}", t, company="NEWAGE", line1="Plot 12, GIDC Estate",
              pincode="382330", gstin=NEWAGE_GSTIN)
    addr = STORE["addresses"]["a-v"]
    client.post("/address/edit/a-v", data=_edit_form(addr, phone="+91 98200 41122"))
    assert STORE["addresses"]["a-v"]["phone"] == "+91 98200 41122"


# ═══ 4. Only ID links count ═════════════════════════════════════════════════

def test_a_name_only_mention_no_longer_blocks_a_plain_delete(client):
    _addr("a-n", "NEWAGE", "vendor", company="NEWAGE FIRE FIGHTING CO. LIMITED")
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "PO-1", "vendor_id": "",
                                  "vendor_name": "NEWAGE FIRE FIGHTING CO. LIMITED"}
    assert AD.linked_of("a-n") == [] and len(AD.mentions_of("a-n")) == 1
    page = client.get("/address/delete/a-n").get_data(as_text=True)
    assert "mentions this name, not linked, not affected" in page
    client.post("/address/delete/a-n")
    assert "a-n" not in STORE["addresses"], "a name-only mention blocked the delete"
    assert STORE["purchases"]["po-1"]["vendor_name"] == "NEWAGE FIRE FIGHTING CO. LIMITED"


def test_the_chip_counts_id_links_only(client):
    _addr("a-c", "NEWAGE", "vendor", company="NEWAGE")
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "PO-1", "vendor_id": "a-c",
                                  "vendor_name": "NEWAGE"}
    STORE["purchases"]["po-2"] = {"id": "po-2", "ref": "PO-2", "vendor_id": "",
                                  "vendor_name": "NEWAGE"}
    html = client.get("/address/").get_data(as_text=True)
    assert "1 linked" in html and "2 refs" not in html


# ═══ 5. MERGE-THEN-DELETE ═══════════════════════════════════════════════════

def _pair_with_links():
    _addr("a-old", "NEWAGE vendor dup", "vendor", company="NEWAGE", line1="Plot 12",
          pincode="382330", gstin=NEWAGE_GSTIN)
    _addr("a-keep", "NEWAGE vendor", "vendor", company="NEWAGE", line1="Plot 12",
          pincode="382330", gstin=NEWAGE_GSTIN)
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "SF/PO/26-27/0001",
                                  "vendor_id": "a-old", "vendor_name": "NEWAGE",
                                  "vendor_gstin": NEWAGE_GSTIN, "status": "issued",
                                  "updated_at": "2026-10-01 10:00", "total": 1180.0}
    STORE["purchase_orders"]["d-1"] = {"id": "d-1", "ref": "SF/DPO/0001",
                                       "vendor_id": "a-old", "vendor_name": "NEWAGE"}


def test_a_linked_delete_page_lists_the_links_and_requires_a_replacement(client):
    _pair_with_links()
    html = client.get("/address/delete/a-old").get_data(as_text=True)
    assert "SF/PO/26-27/0001" in html and "purchases.vendor_id" in html
    assert "purchase_orders.vendor_id" in html
    assert 'name="into" required' in html
    assert "/address/archive/a-old" in html, "archive is not still offered"
    client.post("/address/delete/a-old")
    assert "a-old" in STORE["addresses"], "the plain delete went through a linked address"
    client.post("/address/merge/a-old", data={})
    assert "a-old" in STORE["addresses"], "a merge with no replacement deleted it"
    assert STORE["purchases"]["po-1"]["vendor_id"] == "a-old"


def test_a_vendor_is_refused_as_the_replacement_for_a_site_link(client):
    _addr("a-site", "Whitefield", "site", line1="7 Site Rd", pincode="560066")
    _addr("a-ven", "Some Vendor", "vendor", line1="9 Lane", pincode="400001")
    _addr("a-site2", "Whitefield 2", "site", line1="8 Site Rd", pincode="560066")
    STORE["projects"]["p-1"] = {"id": "p-1", "name": "Sify", "site_address_id": "a-site",
                                "site_address": "Whitefield"}
    page = client.get("/address/merge/a-site").get_data(as_text=True)
    assert 'value="a-ven"' not in page, "a vendor was OFFERED for a site link"
    assert 'value="a-site2"' in page
    client.post("/address/merge/a-site", data={"into": "a-ven"})
    assert "a-site" in STORE["addresses"]
    assert STORE["projects"]["p-1"]["site_address_id"] == "a-site"
    with pytest.raises(AD.MergeRefused):
        AD.merge_into("a-site", "a-ven", "u")


def test_links_no_single_address_can_take_are_explained_and_archive_offered(client):
    _addr("a-mix", "Mixed", "office", line1="7 Rd", pincode="560066")
    _addr("a-ven", "Some Vendor", "vendor", line1="9 Lane", pincode="400001")
    STORE["projects"]["p-1"] = {"id": "p-1", "name": "Sify", "site_address_id": "a-mix"}
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "PO-1", "vendor_id": "a-mix"}
    page = client.get("/address/merge/a-mix").get_data(as_text=True)
    assert "No address can take these links" in page
    assert "/address/archive/a-mix" in page


def test_the_replacement_must_be_active_and_not_itself():
    _pair_with_links()
    with pytest.raises(AD.MergeRefused):
        AD.merge_into("a-old", "a-old", "u")
    STORE["addresses"]["a-keep"]["active"] = False
    with pytest.raises(AD.MergeRefused):
        AD.merge_into("a-old", "a-keep", "u")
    assert STORE["purchases"]["po-1"]["vendor_id"] == "a-old"


def test_an_unlinked_address_is_not_merged_the_plain_delete_stays_owner_only():
    _addr("a-free", "Free", "vendor", line1="1 Rd", pincode="400001")
    _addr("a-k", "Keep", "vendor", line1="2 Rd", pincode="400001")
    with pytest.raises(AD.MergeRefused):
        AD.merge_into("a-free", "a-k", "u")
    assert "a-free" in STORE["addresses"]


def test_an_unlinked_EXACT_duplicate_may_be_merged_and_is_logged():
    """The judgement call: a duplicate pair with no links is cleared from the
    band by the merge (Owner or Director), with a full copy logged."""
    _live_pair()
    entry = AD.merge_into("n-v", "n-o", "u")
    assert "n-v" not in STORE["addresses"]
    assert entry["repointed"] == [] and entry["record"]["label"] == "NEWAGE Vendor"


def test_a_staff_login_allowed_address_delete_may_merge_and_a_block_refuses(client):
    """
    The per-person lists of `/access/` (§0 fifty-sixth block). A Director may
    ALLOW `address.delete` to a staff login; the merge then follows it, and a
    BLOCK takes it away again. Allowing it does not reach the plain delete,
    which is Owner-only.
    """
    _pair_with_links()
    _user(client, "merge-allowed", "role-sales-manager",
          **{auth.PERM_ALLOW_FIELD: ["address.delete"]})
    assert client.get("/address/delete/a-old").status_code == 403
    assert client.get("/address/merge/a-old").status_code == 200
    _user(client, "merge-blocked", "role-sales-manager",
          **{auth.PERM_DENY_FIELD: ["address.delete"]})
    assert client.post("/address/merge/a-old", data={"into": "a-keep"}).status_code == 403
    assert "a-old" in STORE["addresses"]
    _user(client, "merge-allowed", "role-sales-manager",
          **{auth.PERM_ALLOW_FIELD: ["address.delete"]})
    assert client.post("/address/merge/a-old", data={"into": "a-keep"}).status_code == 302
    assert "a-old" not in STORE["addresses"]


def test_the_merge_is_refused_without_address_delete(client):
    _pair_with_links()
    _user(client, "merge-sales", "role-sales-manager")
    for method in ("GET", "POST"):
        r = client.open("/address/merge/a-old", method=method, data={"into": "a-keep"})
        assert r.status_code == 403
    assert "a-old" in STORE["addresses"]


def test_a_per_person_block_on_a_directors_address_delete_refuses_it(client):
    _pair_with_links()
    _user(client, "merge-dir-blocked", "role-director",
          **{auth.PERM_DENY_FIELD: ["address.delete"]})
    r = client.post("/address/merge/a-old", data={"into": "a-keep"})
    assert r.status_code == 403
    assert "a-old" in STORE["addresses"]


def test_a_director_can_merge(client):
    _pair_with_links()
    d = _user(client, "merge-director", "role-director")
    assert client.get("/address/delete/a-old").status_code == 403, (
        "the plain delete stopped being Owner-only")
    r = client.post("/address/merge/a-old", data={"into": "a-keep"})
    assert r.status_code == 302
    assert "a-old" not in STORE["addresses"]
    log = STORE["addresses"]["a-keep"][AD.MERGE_LOG_FIELD][0]
    assert log["by_user_id"] == d["id"], "the log stored something other than the user id"


def test_a_GET_of_the_merge_and_delete_pages_changes_nothing(client):
    _pair_with_links()
    snap = copy.deepcopy({k: STORE.get(k) for k in _TOUCHED + ("addresses",)})
    client.get("/address/merge/a-old?into=a-keep")
    client.get("/address/delete/a-old")
    client.get("/address/")
    assert {k: STORE.get(k) for k in _TOUCHED + ("addresses",)} == snap


def _wide(coll, rid, id_field, aid):
    return {"id": rid, "ref": f"{coll}-ref", id_field: aid,
            "vendor_name": "Typed snapshot", "site": "Snapshot site",
            "site_address": "Snapshot site", "consignee_name": "Snap",
            "contractor_name": "Snap", "to": "Party block\nline 2",
            "status": "issued", "total": 1234.5, "items": [{"qty": 2}],
            "created_at": "2026-10-01 10:00", "updated_at": "2026-10-02 11:00"}


def test_a_merged_record_differs_ONLY_in_its_id_field():
    _addr("a-old", "Old", "site", line1="1 Rd", pincode="400001")
    _addr("a-keep", "Keep", "site", line1="2 Rd", pincode="400001")
    # Every collection's type need is satisfied by a site, except vendor and
    # contractor links: those get their own pair below.
    site_like = [c for c, *_ in AD.REFERENCE_SOURCES
                 if AD.LINK_TYPES[c] is None or "site" in AD.LINK_TYPES[c]]
    fields = {c: f for c, f, *_ in AD.REFERENCE_SOURCES}
    for c in site_like:
        STORE[c]["r-1"] = _wide(c, "r-1", fields[c], "a-old")
    before = copy.deepcopy({c: STORE[c]["r-1"] for c in site_like})
    entry = AD.merge_into("a-old", "a-keep", "user-1")
    for c in site_like:
        after = STORE[c]["r-1"]
        changed = {k for k in set(after) | set(before[c]) if after.get(k) != before[c].get(k)}
        assert changed == {fields[c]}, f"{c}: the merge changed {changed}"
        assert after[fields[c]] == "a-keep"
    assert sorted((p["collection"], p["id"], p["field"]) for p in entry["repointed"]) == \
        sorted((c, "r-1", fields[c]) for c in site_like)
    for t, colls in (("vendor", ("purchases", "purchase_orders")),
                     ("contractor", ("work_orders",))):
        _addr(f"o-{t}", "Old", t, line1="3 Rd", pincode="400001")
        _addr(f"k-{t}", "Keep", t, line1="4 Rd", pincode="400001")
        for c in colls:
            STORE[c]["r-1"] = _wide(c, "r-1", fields[c], f"o-{t}")
        before = copy.deepcopy({c: STORE[c]["r-1"] for c in colls})
        AD.merge_into(f"o-{t}", f"k-{t}", "user-1")
        for c in colls:
            after = STORE[c]["r-1"]
            changed = {k for k in set(after) | set(before[c])
                       if after.get(k) != before[c].get(k)}
            assert changed == {fields[c]}, f"{c}: the merge changed {changed}"


def test_the_merge_log_holds_ids_time_repoints_and_a_full_copy():
    _pair_with_links()
    old = copy.deepcopy(STORE["addresses"]["a-old"])
    entry = AD.merge_into("a-old", "a-keep", "user-xyz")
    assert entry["by_user_id"] == "user-xyz"
    assert entry["from_id"] == "a-old" and entry["to_id"] == "a-keep" and entry["at"]
    assert entry["record"] == old
    assert {(p["collection"], p["id"], p["field"]) for p in entry["repointed"]} == {
        ("purchases", "po-1", "vendor_id"), ("purchase_orders", "d-1", "vendor_id")}
    assert STORE["addresses"]["a-keep"][AD.MERGE_LOG_FIELD] == [entry]


def test_a_rerun_after_a_partial_persist_finishes_with_no_double_effect(client):
    """
    Scenario 1: the `addresses` sync landed (old deleted, log on the survivor)
    but `purchases` did not, and the process restarted, so the PO came back
    pointing at the deleted id. The register shows the unfinished merge, and
    running it again repoints only the PO.
    """
    _pair_with_links()
    AD.merge_into("a-old", "a-keep", "u1")
    STORE["purchases"]["po-1"]["vendor_id"] = "a-old"         # the reverted collection
    dpo = copy.deepcopy(STORE["purchase_orders"]["d-1"])
    page = client.get("/address/").get_data(as_text=True)
    assert "A merge did not finish" in page
    assert client.get("/address/merge/a-old").status_code == 200
    client.post("/address/merge/a-old", data={"into": "a-keep"})
    assert STORE["purchases"]["po-1"]["vendor_id"] == "a-keep"
    assert STORE["purchase_orders"]["d-1"] == dpo
    log = STORE["addresses"]["a-keep"][AD.MERGE_LOG_FIELD]
    assert len(log) == 1, "the re-run added a second log entry"
    assert len(log[0]["repointed"]) == 2, "the re-run logged a repoint twice"
    assert AD.unfinished_merges() == []
    # And once more, with nothing left: still no double effect.
    AD.merge_into("a-old", "a-keep", "u1")
    assert len(log) == 1 and len(log[0]["repointed"]) == 2


def test_a_rerun_after_the_address_sync_failed_finishes_too():
    """
    Scenario 2: the documents persisted, `addresses` did not (old record back,
    no log). Running the merge again deletes the old record and repoints
    nothing twice.
    """
    _pair_with_links()
    old = copy.deepcopy(STORE["addresses"]["a-old"])
    keep = copy.deepcopy(STORE["addresses"]["a-keep"])
    AD.merge_into("a-old", "a-keep", "u1")
    STORE["addresses"]["a-old"] = old                         # the reverted collection
    STORE["addresses"]["a-keep"] = keep
    docs = copy.deepcopy((STORE["purchases"], STORE["purchase_orders"]))
    AD.merge_into("a-old", "a-keep", "u1")
    assert "a-old" not in STORE["addresses"]
    assert (STORE["purchases"], STORE["purchase_orders"]) == docs


# ═══ 6. Print is byte-identical across a merge ══════════════════════════════

def _swap_print(client, url, coll, rid, field, atype, extra=()):
    _addr("p-old", "Old party", atype, line1="11 Print Rd", pincode="400001")
    _addr("p-keep", "Kept party", atype, line1="12 Print Rd", pincode="400001",
          company="A DIFFERENT NAME")
    STORE[coll][rid][field] = "p-old"
    before = client.get(url).get_data(as_text=True)
    assert len(before) > 5000
    AD.merge_into("p-old", "p-keep", "u")
    assert STORE[coll][rid][field] == "p-keep"
    after = client.get(url).get_data(as_text=True)
    assert after == before, f"{url} printed differently after the merge"
    for label in extra:
        assert label in after
    return after


def test_the_purchase_order_prints_the_same_after_a_merge(client, golden):
    _swap_print(client, f"/purchase/view/{GOLD_PO}", "purchases", GOLD_PO, "vendor_id",
                "vendor")


def test_the_draft_po_prints_the_same_after_a_merge(client, golden_dpo):
    _swap_print(client, f"/po/print/{GOLD_DPO}", "purchase_orders", GOLD_DPO,
                "vendor_id", "vendor")


def test_the_challan_prints_the_same_after_a_merge_copy_labels_and_all(client, golden_dc):
    import docsheet as DS
    _swap_print(client, f"/dc/print/{GOLD_DC}", "delivery_challans", GOLD_DC,
                "consignee_id", "site", extra=DS.COPIES_DC)


def test_the_work_order_prints_the_same_after_a_merge(client, golden_wo):
    _swap_print(client, f"/wo/print/{GOLD_WO}", "work_orders", GOLD_WO,
                "contractor_id", "contractor")


# ═══ 7. The picker filters and the merge's filter are ONE table ═════════════

def test_each_picker_reads_its_types_from_address_py():
    assert workorder.CONTRACTOR_TYPES is AD.CONTRACTOR_TYPES
    assert EMP.SITE_TYPES is AD.SITE_TYPES
    assert purchase.VENDOR_TYPES is AD.VENDOR_TYPES
    assert po_draft.VENDOR_TYPES is AD.VENDOR_TYPES
    assert challan.CONSIGNEE_TYPES is AD.CONSIGNEE_TYPES
    import pathlib
    root = pathlib.Path(AD.__file__).parent
    for f in ("purchase.py", "po_draft.py"):
        src = (root / f).read_text(encoding="utf-8")
        assert 'only_types=("vendor",)' not in src, f"{f} carries its own copy again"
        assert "only_types=VENDOR_TYPES" in src
    assert "only_types=CONSIGNEE_TYPES" in (root / "challan.py").read_text(encoding="utf-8")
    assert set(AD.LINK_TYPES) == {c for c, *_ in AD.REFERENCE_SOURCES}
    assert AD.LINK_TYPES["projects"] is AD.SITE_TYPES
    assert AD.LINK_TYPES["employees"] is AD.SITE_TYPES
    assert AD.LINK_TYPES["attendance"] is AD.SITE_TYPES
    assert AD.LINK_TYPES["purchases"] is AD.VENDOR_TYPES
    assert AD.LINK_TYPES["purchase_orders"] is AD.VENDOR_TYPES
    assert AD.LINK_TYPES["work_orders"] is AD.CONTRACTOR_TYPES
    assert AD.LINK_TYPES["delivery_challans"] is AD.CONSIGNEE_TYPES


# ═══ 8. The register's amber band ═══════════════════════════════════════════

def _live_pair():
    _addr("n-o", "NEWAGE Office", "office", company="NEWAGE FIRE FIGHTING CO. LIMITED",
          line1="Plot 12, GIDC Estate", pincode="382330", gstin=NEWAGE_GSTIN)
    _addr("n-v", "NEWAGE Vendor", "vendor", company="NEWAGE FIRE FIGHTING CO. LIMITED",
          line1="Plot 12 GIDC Estate", pincode="382 330", gstin=NEWAGE_GSTIN)


def test_the_band_lists_the_live_pair_with_merge_links(client):
    _live_pair()
    groups = AD.duplicate_groups()
    assert any({a["id"] for a in g} == {"n-o", "n-v"} for g in groups)
    snap = copy.deepcopy(STORE["addresses"])
    html = client.get("/address/").get_data(as_text=True)
    assert STORE["addresses"] == snap, "the band changed something on a GET"
    assert "duplicate addresses" in html
    assert "/address/merge/n-o?into=n-v" in html
    assert "/address/merge/n-v?into=n-o" in html


def test_the_band_offers_a_merge_link_only_where_the_target_takes_the_links(client):
    """The vendor holds a PO link; an office cannot take it, so no link from
    the vendor to the office is drawn, and the reason is said instead."""
    _live_pair()
    STORE["purchases"]["po-1"] = {"id": "po-1", "ref": "PO-1", "vendor_id": "n-v"}
    html = client.get("/address/").get_data(as_text=True)
    assert "/address/merge/n-v?into=n-o" not in html
    assert "/address/merge/n-o?into=n-v" in html
    assert "no other record in this group can take its links" in html


def test_the_branch_refusal_says_so_at_the_top_of_the_form(client):
    _addr("a-hq", "NEWAGE HQ", company="NEWAGE", line1="Plot 12, GIDC Estate",
          pincode="382330", gstin=NEWAGE_GSTIN)
    html = client.post("/address/add", data=_form(
        label="Vapi", line1="Shed 4", pincode="396195")).get_data(as_text=True)
    assert html.index("Not saved yet") < html.index('name="branch_ok"')


def test_the_band_is_for_address_delete_holders_only(client):
    _live_pair()
    _user(client, "band-sales", "role-sales-manager")
    html = client.get("/address/").get_data(as_text=True)
    assert "duplicate addresses" not in html
    _user(client, "band-director", "role-director")
    assert "duplicate addresses" in client.get("/address/").get_data(as_text=True)


def test_no_em_dash_in_the_new_user_facing_strings():
    for kind in ("exact", "branch"):
        assert "—" not in AD.duplicate_message(kind, [{"label": "x", "type": "office"}])
    import ast
    import inspect
    import textwrap
    for fn in (AD._dup_refusal_html, AD._branch_tick_html, AD._merge_body,
               AD._mention_chips, AD._duplicates_band, AD.merge_into,
               AD.why_no_candidates, AD.merge_address, AD._mentions_sentence,
               AD._needs_note, AD.duplicate_message, AD._link_rows):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        doc = ast.get_docstring(tree.body[0], clean=False)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == doc:
                    continue
                assert "—" not in node.value and "&mdash;" not in node.value, (
                    f"{fn.__name__}: {node.value[:80]!r}")
