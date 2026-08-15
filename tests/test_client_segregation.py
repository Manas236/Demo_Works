"""
Client-wise segregation, and the minimal party edit — CLIENT_CHANGES.md item 2.

The page is a **per-client outstanding ledger**, which is the reason its
arithmetic is worth pinning this hard: every figure on it is one somebody is
about to chase a customer for.

Eight things this feature has to get right, and each is a section below:

  1. it groups BOQs by the billed-to party, and totals them;
  2. it **reports** near-duplicate names and never merges them;
  3. outstanding **excludes draft and cancelled bills**;
  4. the party edit writes the party block and **nothing else**;
  5. a draft or issued bill **locks** those fields;
  6. a **cancelled bill alone does not** — and the divergence is surfaced;
  7. a GET on a locked BOQ **renders read-only**, naming the blocking bills;
  8. the totals follow the whole revision chain.

⚠ Cases 3 and 4 are the load-bearing pair and neither existed. Without 3 a
  withdrawn claim inflates a figure presented as a debt; without 4 nothing
  stops the "minimal" edit route growing into the general BOQ edit that
  CLIENT_CHANGES.md item 2 explicitly says it must not become.
"""

import copy

import pytest

import ra
from store import STORE


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(client):
    """The seeded Sify schedule, with no bills and no receipts against it."""
    client.get("/boq/")
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()
    bid = next(b for b, rec in STORE["boqs"].items() if not rec.get("supersedes"))
    yield bid
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()


def _bill(boq_id, ra_no, status, total, rid=None, **extra):
    """One RA bill against a BOQ, in a chosen lifecycle state."""
    rid = rid or f"bill-{ra_no}"
    boq = STORE["boqs"][boq_id]
    STORE["ra_bills"][rid] = dict({
        "id": rid, "ref": f"SF/RA/26-27/{ra_no:04d}", "fy": "26-27",
        "date": "2026-08-10", "boq_id": boq_id,
        "boq_ref": boq.get("ref", ""), "boq_rev_no": boq.get("rev_no", 0),
        "ra_no": ra_no, "leg": "supply", "claims": [],
        "claim_subtotal": total, "deductions": [], "deduction_total": 0.0,
        "net_payable": total, "grand_total": total,
        "account_name": boq.get("account_name", ""),
        "contact_person": boq.get("contact_person", ""),
        "to": boq.get("to", ""), "bill_gstin": boq.get("bill_gstin", ""),
        "project_name": boq.get("project_name", ""),
        "site_location": boq.get("site_location", ""),
        "status": status, "issued_on": "", "cancelled_on": "",
        "cancel_reason": "withdrawn in error" if status == "cancelled" else "",
        "notes": "",
    }, **extra)
    return rid


def _receipt(ra_id, boq_id, amount, rcid="rc-1"):
    STORE["receipts"][rcid] = {
        "id": rcid, "ref": "SF/RCPT/26-27/0001", "fy": "26-27",
        "date": "2026-08-12", "ra_id": ra_id, "ra_ref": "SF/RA/26-27/0001",
        "ra_no": 1, "leg": "supply", "boq_id": boq_id,
        "boq_ref": "SF/BOQ/26-27/0001", "project_name": "Sify",
        "account_name": "", "amount": float(amount), "mode": "neft",
        "instrument_ref": "UTR1", "instrument_date": "", "notes": "",
    }
    return rcid


def _second_boq(src_id, new_id, **over):
    rec = copy.deepcopy(STORE["boqs"][src_id])
    rec.update({"id": new_id, "supersedes": ""}, **{})
    rec.update(over)
    STORE["boqs"][new_id] = rec
    return new_id


# ═══ 1. Grouping and totals ════════════════════════════════════════════════

def test_the_register_renders_and_groups_by_the_billed_to_party(client, seeded):
    html = client.get("/client/").get_data(as_text=True)
    assert "Prudent Teqtis Pvt Ltd" in html
    assert "SF/BOQ/26-27/0001" in html
    assert "Client" in html and "Register" in html


def test_two_schedules_for_one_client_land_in_one_group(client, seeded):
    _second_boq(seeded, "boq-2", ref="SF/BOQ/26-27/0002",
                project_name="Sify Chennai", subtotal=500000.0)
    html = client.get("/client/").get_data(as_text=True)

    assert html.count('class="cl-group"') == 1, "one client, one panel"
    assert "SF/BOQ/26-27/0002" in html and "SF/BOQ/26-27/0001" in html
    assert "2 schedules" in html


def test_a_boq_with_no_customer_name_is_left_out_entirely(client, seeded):
    """
    A blank name is not a client called "". Grouping on it would invent one and
    file everybody's unnamed schedules under it.
    """
    _second_boq(seeded, "boq-nameless", ref="SF/BOQ/26-27/0003",
                account_name="   ")
    html = client.get("/client/").get_data(as_text=True)
    assert "SF/BOQ/26-27/0003" not in html


# ═══ 2. Near-duplicates are REPORTED, never merged ═════════════════════════

def test_near_duplicate_names_warn_and_stay_in_separate_groups(client, seeded):
    """
    DOMAIN.md §6. Two spellings may be one party; this app does not know that,
    and merging them would be it deciding. It says so and leaves them apart.
    """
    _second_boq(seeded, "boq-dup", ref="SF/BOQ/26-27/0002",
                account_name="Prudent Teqtis Pvt. Ltd.")
    html = client.get("/client/").get_data(as_text=True)

    assert 'class="cl-dup"' in html, "no near-duplicate band"
    assert "Prudent Teqtis Pvt Ltd" in html
    assert "Prudent Teqtis Pvt. Ltd." in html
    assert html.count('class="cl-group"') == 2, "the two names were merged"


def test_a_name_that_differs_only_in_case_and_spacing_IS_one_group(client, seeded):
    """
    `norm_name` casefolds and collapses whitespace, so these are genuinely the
    same key rather than a judgement about two different strings.
    """
    _second_boq(seeded, "boq-case", ref="SF/BOQ/26-27/0002",
                account_name="  prudent   teqtis PVT ltd ")
    html = client.get("/client/").get_data(as_text=True)
    assert html.count('class="cl-group"') == 1
    assert 'class="cl-dup"' not in html


# ═══ 3. Outstanding excludes DRAFT and CANCELLED ═══ (load-bearing) ════════

def test_outstanding_counts_issued_bills_only(client, seeded):
    """
    ⚠ **The load-bearing one.** A draft has not been sent and a cancelled bill
      has been withdrawn, so neither is money anybody owes. This page is a
      per-client outstanding ledger: a figure here is one somebody is about to
      chase a customer for, and a withdrawn claim inside it is a demand for
      money that was explicitly retracted.
    """
    _bill(seeded, 1, "issued", 100000.0)
    _bill(seeded, 2, "draft", 55000.0)
    _bill(seeded, 3, "cancelled", 77000.0)

    from client import _client_groups
    groups, _dups = _client_groups()
    grp = next(iter(groups.values()))

    assert grp["total_issued"] == 100000.0, (
        "the draft, the cancelled bill, or both were counted as issued")
    assert grp["total_outstanding"] == 100000.0
    assert grp["total_received"] == 0.0


def test_receipts_reduce_outstanding_and_an_overpayment_shows_as_credit(client, seeded):
    rid = _bill(seeded, 1, "issued", 100000.0)
    _receipt(rid, seeded, 130000.0)

    from client import _client_groups
    grp = next(iter(_client_groups()[0].values()))
    assert grp["total_received"] == 130000.0
    assert grp["total_outstanding"] == -30000.0, "an overpayment was clamped at zero"

    html = client.get("/client/").get_data(as_text=True)
    assert "in credit" in html


def test_the_totals_follow_the_whole_revision_chain(client, seeded):
    """
    `ra.bills_of()` and `receipt.receipts_of_boq()` both walk the chain. Summing
    against one record would reset a client's position to zero on every
    revision — silently, and only on projects that have been revised.
    """
    rid = _bill(seeded, 1, "issued", 100000.0)
    _receipt(rid, seeded, 40000.0)

    rev = _second_boq(seeded, "boq-rev1", ref="SF/BOQ/26-27/0001",
                      rev_no=1, subtotal=0.0)
    STORE["boqs"][rev]["supersedes"] = seeded

    from client import _client_groups
    groups = _client_groups()[0]
    grp = next(iter(groups.values()))
    # Both records are in the group; the bill and the receipt are counted ONCE
    # each from whichever record's chain they were reached through — the point
    # is that the revision did not lose them.
    assert grp["total_issued"] >= 100000.0
    assert grp["total_received"] >= 40000.0


# ═══ 4. The edit touches the party block and NOTHING else ═══ (load-bearing)

def test_the_party_edit_does_not_touch_lines_rates_or_project_fields(client, seeded):
    """
    ⚠ **The other load-bearing one.** CLIENT_CHANGES.md item 2 says in as many
      words that this is a minimal route and "must not become" the general BOQ
      edit. Nothing but a test stops it drifting into one, and by the time it
      has, a customer-name correction is silently rewriting a priced schedule.
    """
    boq = STORE["boqs"][seeded]
    before = {
        "line_items": copy.deepcopy(boq["line_items"]),
        "sections": copy.deepcopy(boq["sections"]),
        "subtotal": boq["subtotal"],
        "supply_subtotal": boq["supply_subtotal"],
        "install_subtotal": boq["install_subtotal"],
        "project_name": boq["project_name"],
        "site_location": boq["site_location"],
        "ref": boq["ref"], "date": boq["date"], "rev_no": boq["rev_no"],
        "rate_basis_label": boq["rate_basis_label"],
    }

    # Post the party fields AND a full set of decoys naming everything this
    # route must refuse to write.
    r = client.post(f"/client/edit-party/{seeded}", data={
        "account_name": "Renamed Contractor Pvt Ltd",
        "contact_person": "Ms A Rao",
        "bill_city": "Pune", "bill_state": "Maharashtra",
        # decoys:
        "project_name": "HACKED PROJECT",
        "site_location": "HACKED SITE",
        "ref": "SF/BOQ/99-99/9999",
        "date": "1999-01-01",
        "rev_no": "9",
        "rate_basis_label": "HACKED RATES",
        "subtotal": "1",
        "boq_json": '{"lines": []}',
    })
    assert r.status_code == 302

    after = STORE["boqs"][seeded]
    assert after["account_name"] == "Renamed Contractor Pvt Ltd"
    assert after["contact_person"] == "Ms A Rao"
    assert after["bill_city"] == "Pune"

    for key, was in before.items():
        assert after[key] == was, f"the party edit changed {key}"


def test_the_party_edit_updates_every_party_field_it_owns(client, seeded):
    r = client.post(f"/client/edit-party/{seeded}", data={
        "account_name": "New Party Ltd", "contact_person": "Jane Doe",
        "bill_addr": "123 New St", "bill_city": "Mumbai",
        "bill_state": "Maharashtra", "bill_pin": "400001",
        "bill_phone": "9999999999", "bill_gstin": "27AAAAA0000A1Z5",
        "ship_acct_name": "Site Office", "ship_addr": "Site Addr",
        "ship_city": "Pune", "ship_state": "Maharashtra", "ship_pin": "411001",
    })
    assert r.status_code == 302
    boq = STORE["boqs"][seeded]
    assert boq["account_name"] == "New Party Ltd"
    assert boq["bill_gstin"] == "27AAAAA0000A1Z5"
    assert boq["ship_city"] == "Pune"
    assert boq["ship_same"] is False
    assert "New Party Ltd" in boq["to"], "the printable block was not rebuilt"


def test_a_blank_account_name_is_refused(client, seeded):
    before = STORE["boqs"][seeded]["account_name"]
    r = client.post(f"/client/edit-party/{seeded}", data={"account_name": "  "})
    assert r.status_code == 200
    assert "needs a customer account name" in r.get_data(as_text=True)
    assert STORE["boqs"][seeded]["account_name"] == before


# ═══ 5. The lock ═══════════════════════════════════════════════════════════

@pytest.mark.parametrize("status", ["draft", "issued"])
def test_a_draft_or_issued_bill_locks_the_party_fields(client, seeded, status):
    _bill(seeded, 1, status, 100000.0)
    before = STORE["boqs"][seeded]["account_name"]

    r = client.post(f"/client/edit-party/{seeded}",
                    data={"account_name": "Hack Attempt"})
    assert r.status_code == 302
    assert "cannot be edited" in r.headers["Location"].replace("+", " ").replace("%20", " ")
    assert STORE["boqs"][seeded]["account_name"] == before


def test_a_get_on_a_locked_boq_renders_the_form_read_only(client, seeded):
    """
    Step 5a. It used to redirect on GET as well as POST, so a locked schedule's
    customer details could not even be looked at from here. Refusing a change
    and refusing to show it are different acts.
    """
    _bill(seeded, 1, "issued", 100000.0, rid="lockbill")
    r = client.get(f"/client/edit-party/{seeded}")

    assert r.status_code == 200, "a GET on a locked BOQ still bounces"
    html = r.get_data(as_text=True)
    assert "locked and shown read-only" in html
    assert "disabled" in html
    assert 'name="account_name"' in html
    assert "Prudent Teqtis Pvt Ltd" in html, "the current details are not shown"
    # The blocking bill is NAMED and LINKED, not merely counted.
    assert "SF/RA/26-27/0001" in html
    assert f"/ra/view/lockbill" in html
    # And there is no way to submit it.
    assert "Save party details" not in html


def test_an_unlocked_boq_still_offers_the_save_button(client, seeded):
    html = client.get(f"/client/edit-party/{seeded}").get_data(as_text=True)
    assert "Save party details" in html
    assert "locked and shown read-only" not in html


# ═══ 6. A CANCELLED bill alone does not lock ═══════════════════════════════

def test_a_cancelled_bill_alone_does_not_lock_the_party_fields(client, seeded):
    """
    ⚠ **This narrows a rule set on 10 August 2026.** A cancelled bill can never
      be deleted and never un-cancelled, so counting it froze that BOQ's
      customer name **permanently, with no escape** — and that client stayed
      split across two rows of `/client/` forever. A cancelled bill is excluded
      from every other total in this app by design; it should not be the one
      thing freezing master data.
    """
    _bill(seeded, 1, "cancelled", 77000.0)
    assert ra.party_lock_bills(seeded) == []

    assert client.get(f"/client/edit-party/{seeded}").status_code == 200
    r = client.post(f"/client/edit-party/{seeded}",
                    data={"account_name": "Corrected Name Pvt Ltd"})
    assert r.status_code == 302
    assert STORE["boqs"][seeded]["account_name"] == "Corrected Name Pvt Ltd"


def test_a_cancelled_bill_beside_an_issued_one_still_locks(client, seeded):
    """The narrowing is about a cancelled bill ALONE, not about ignoring them."""
    _bill(seeded, 1, "cancelled", 77000.0, rid="b-void")
    _bill(seeded, 2, "issued", 100000.0, rid="b-live")

    locking = ra.party_lock_bills(seeded)
    assert [rid for rid, _b in locking] == ["b-live"]

    r = client.post(f"/client/edit-party/{seeded}",
                    data={"account_name": "Hack Attempt"})
    assert r.status_code == 302
    assert STORE["boqs"][seeded]["account_name"] != "Hack Attempt"


def test_ra_view_flags_a_party_that_has_moved_under_an_issued_bill(client, seeded):
    """
    The divergence surface the receipts work established, one field over. The
    bill keeps its own frozen copy and is deliberately not restated — but a
    disagreement nobody can see is worse than one everybody can (DOMAIN.md §6).
    """
    rid = _bill(seeded, 1, "cancelled", 77000.0)
    assert not ra.party_drift(STORE["ra_bills"][rid])

    r = client.post(f"/client/edit-party/{seeded}",
                    data={"account_name": "Corrected Name Pvt Ltd"})
    assert r.status_code == 302

    drift = ra.party_drift(STORE["ra_bills"][rid])
    assert ("Customer", "Prudent Teqtis Pvt Ltd", "Corrected Name Pvt Ltd") in drift

    html = client.get(f"/ra/view/{rid}").get_data(as_text=True)
    assert "customer details have been edited" in html
    assert "Corrected Name Pvt Ltd" in html
    assert "Prudent Teqtis Pvt Ltd" in html
    assert "not</b> restated" in html or "not restated" in html


def test_the_printed_bill_does_not_move_when_the_party_is_corrected(client, seeded):
    """
    The whole reason the divergence is only *flagged*: a document that has gone
    out says what it said. Byte-identical, the same assertion
    `tests/test_receipts.py` makes about a corrected receipt.
    """
    rid = _bill(seeded, 1, "cancelled", 77000.0)
    before = client.get(f"/ra/print/{rid}").get_data(as_text=True)

    client.post(f"/client/edit-party/{seeded}",
                data={"account_name": "Corrected Name Pvt Ltd",
                      "bill_gstin": "27ZZZZZ9999Z9Z9"})

    assert client.get(f"/ra/print/{rid}").get_data(as_text=True) == before


# ═══ 7. The register's own controls ════════════════════════════════════════

def test_the_register_labels_the_control_view_when_the_boq_is_locked(client, seeded):
    html = client.get("/client/").get_data(as_text=True)
    assert "Edit party" in html

    _bill(seeded, 1, "issued", 100000.0)
    html = client.get("/client/").get_data(as_text=True)
    assert "View party" in html, "a locked schedule still offered to edit"
