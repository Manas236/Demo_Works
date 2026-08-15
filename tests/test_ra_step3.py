"""
The RA register, and the lifecycle that replaced certification.

Four tests in this file used to cover `/ra/certify/<id>` and the certification
badge. Certification was removed entirely (CLIENT_CHANGES.md item 3), so those
four went with the feature they tested; the deletions are named in the commit.
What replaced them is below, and it is more than a rename: certification was
doing double duty as the lock that stopped an issued bill being edited, and the
lock is what the tests here exist to hold.

Three properties everything here circles:

- **A draft is ours; an issued bill is not.** Issue is the moment the document
  stops being editable and stops being deletable.
- **Cancelling is not deleting.** The record survives, the number stays spent,
  and the claim's quantity goes back onto the balance.
- **A GET never changes a state.** Both lifecycle routes confirm on GET and
  mutate only in the POST branch — and §7.9f's `url_map` sweep does not cover
  either of them, because it only walks rules whose path contains "delete".
"""

import pytest

import boq as BQ
import ra
from store import STORE
from test_ra_record import boq_line, make_boq, make_bill, claim


@pytest.fixture()
def clean_store(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()
    STORE["_boq_seeded"] = False
    yield STORE
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["receipts"].clear()


def test_register_renders_for_zero_bills(client, clean_store):
    res = client.get("/ra/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Register" in html
    assert "No Running Account bills yet" in html


def test_register_renders_for_one_and_many_bills(client, clean_store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    make_bill("r2", "b1", 2, "installation", [claim("1", 20)])

    res = client.get("/ra/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "RA1" in html
    assert "RA2" in html
    assert "supply" in html
    assert "installation" in html
    assert "Latest" in html


# ═══════════════════════════════════════════════════════════════════════════
# THE STATUS BADGE — three states, and no certification anywhere
# ═══════════════════════════════════════════════════════════════════════════

def test_the_three_states_each_render_their_own_badge(clean_store):
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)], status="draft")
    make_bill("r2", "b1", 2, "supply", [claim("1", 20)], status="issued")
    make_bill("r3", "b1", 3, "supply", [claim("1", 10)], status="cancelled")

    assert "Draft" in ra.status_badge(STORE["ra_bills"]["r1"])
    assert "Issued" in ra.status_badge(STORE["ra_bills"]["r2"])
    assert "Cancelled" in ra.status_badge(STORE["ra_bills"]["r3"])


def test_a_bill_with_no_status_key_reads_as_issued_not_draft(clean_store):
    """
    THE safe default. A record written before the field existed, and the two
    statuses this app used to write in its place, all mean *it has gone to the
    main contractor*. Reading any of them as `draft` would silently reopen every
    historical bill to editing and deletion — the exact failure the lock exists
    to prevent.
    """
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30)])
    bill = STORE["ra_bills"]["r1"]
    bill.pop("status", None)

    assert ra.status_of(bill) == "issued"
    assert ra.is_issued(bill) is True
    assert ra.can_edit(bill)[0] is False

    for legacy in ("submitted", "certified"):
        bill["status"] = legacy
        assert ra.status_of(bill) == "issued", legacy
        assert ra.can_edit(bill)[0] is False, legacy


# ═══════════════════════════════════════════════════════════════════════════
# THE REGISTER EXCLUDES CANCELLED MONEY
# ═══════════════════════════════════════════════════════════════════════════

def test_the_register_totals_exclude_a_cancelled_bill(client, clean_store):
    """
    A withdrawn claim is not a smaller claim — it contributes nothing. The count
    of cancelled bills is still shown, because a total that silently drops
    records is one nobody can reconcile against the table under it.
    """
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30, rate=100.0)],
              status="issued")
    make_bill("r2", "b1", 2, "supply", [claim("1", 20, rate=100.0)],
              status="cancelled", cancelled_on="2026-08-14",
              cancel_reason="remeasured")

    html = client.get("/ra/").get_data(as_text=True)
    assert "1 live running account bill" in html
    assert "1 cancelled, excluded" in html
    # RA1's 3,000 stands alone; RA2's 2,000 is not added to it.
    assert "3,000" in html
    assert "5,000" not in html


def test_the_boq_page_does_not_show_a_cancelled_bills_money_as_live(client,
                                                                   clean_store):
    """
    `/boq/view` reads `STORE["ra_bills"]` directly — boq.py may never import
    ra.py — so it needs its own answer to "is this one cancelled". A withdrawn
    claim printed at full value alongside the live ones invites the reader to
    add the strip up and get a total the project does not owe.
    """
    make_boq("b1", [boq_line("1", 100)])
    make_bill("r1", "b1", 1, "supply", [claim("1", 30, rate=100.0)],
              status="issued")
    make_bill("r2", "b1", 2, "supply", [claim("1", 20, rate=100.0)],
              status="cancelled", cancelled_on="2026-08-15",
              cancel_reason="remeasured")

    html = client.get("/boq/view/b1").get_data(as_text=True)
    assert "RA1" in html and "RA2" in html      # both still listed
    assert "cancelled" in html                   # and RA2 says which it is
    # RA2's grand total does not appear as a figure on the strip.
    void_total = float(STORE["ra_bills"]["r2"]["grand_total"])
    assert f"{void_total:,.0f}" not in html.split('class="ra-strip"')[1][:600]
