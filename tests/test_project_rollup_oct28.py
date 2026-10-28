"""
The two project-page bugs from the 28 October 2026 Yogesh meeting.

1. **Revisions were stacked.** Attach walks the whole revision chain, so every
   revision of one schedule sat on the project, and the BOQ panel's total
   added them all: Rev 0 + Rev 1 of one schedule read as two schedules. Only
   the latest revision may count; the superseded ones stay listed.

2. **Documents raised from a BOQ did not follow it.** Each copied the BOQ's
   `project_id` once at create (the proforma never at all), so a BOQ attached
   to its project AFTER its documents were raised left them on no project.
   `pnl.project_of()` now derives it live, and the page, the P&L and the
   untagged-cost line all read it.
"""

import re

from store import STORE
import pnl as PNL


def _page(client, pid="p1"):
    r = client.get(f"/projects/view/{pid}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _boq_total(html: str) -> str:
    """The BOQ panel's Total cell — the first total row on the page after the
    Bills of Quantities heading."""
    seg = html.split("<h2>Bills of Quantities</h2>", 1)[1]
    m = re.search(r'<tr class="total-row"><td colspan="4">Total</td>'
                  r'<td style="text-align:right;">([^<]*)</td>', seg)
    assert m, "BOQ panel has no total row"
    return m.group(1)


def _project():
    STORE["projects"]["p1"] = {"id": "p1", "name": "Jamnagar", "norm_name": "jamnagar"}


def _chain(pid="p1"):
    """One schedule, two revisions: Rev 0 at 1,00,000 superseded by Rev 1 at
    1,50,000. Both attached, as attach leaves them."""
    STORE["boqs"]["b0"] = {"id": "b0", "ref": "SF/BOQ/26-27/0019", "rev_no": 0,
                           "supersedes": "", "date": "2026-10-01",
                           "subtotal": 100000.0, "project_id": pid, "line_items": []}
    STORE["boqs"]["b1"] = {"id": "b1", "ref": "SF/BOQ/26-27/0020", "rev_no": 1,
                           "supersedes": "b0", "date": "2026-10-10",
                           "subtotal": 150000.0, "project_id": pid, "line_items": []}


# =============================================================================
# 1. REVISIONS ARE NOT STACKED
# =============================================================================

def test_boq_total_counts_only_the_latest_revision(client):
    _project()
    _chain()
    html = _page(client)
    assert _boq_total(html) == "1,50,000.00", "Rev 0 + Rev 1 must not be summed"


def test_superseded_revision_is_still_listed_and_named(client):
    _project()
    _chain()
    html = _page(client)
    assert "SF/BOQ/26-27/0019" in html, "the superseded revision stays visible"
    assert "superseded by Rev 1" in html
    assert "1 superseded revision listed for reference" in html


def test_two_separate_schedules_still_add_up(client):
    """The control: two DIFFERENT chains on one project are two schedules and
    their tips are summed — only revisions of ONE chain collapse."""
    _project()
    _chain()
    STORE["boqs"]["c0"] = {"id": "c0", "ref": "SF/BOQ/26-27/0030", "rev_no": 0,
                           "supersedes": "", "date": "2026-10-12",
                           "subtotal": 50000.0, "project_id": "p1", "line_items": []}
    assert _boq_total(_page(client)) == "2,00,000.00"


def test_no_superseded_note_without_revisions(client):
    _project()
    STORE["boqs"]["c0"] = {"id": "c0", "ref": "SF/BOQ/26-27/0030", "rev_no": 0,
                           "supersedes": "", "date": "2026-10-12",
                           "subtotal": 50000.0, "project_id": "p1", "line_items": []}
    html = _page(client)
    assert "superseded" not in html
    assert _boq_total(html) == "50,000.00"


# =============================================================================
# 2. DOCUMENTS FOLLOW THEIR BOQ
# =============================================================================

def test_project_of_follows_the_boq_not_the_stored_snapshot(client):
    _project()
    _chain()
    # Raised while the BOQ was on no project: the snapshot is blank.
    po = {"id": "po1", "boq_id": "b1", "project_id": ""}
    assert PNL.project_of(po) == "p1"
    # And the BOQ moving takes the PO with it.
    STORE["projects"]["p2"] = {"id": "p2", "name": "Other", "norm_name": "other"}
    STORE["boqs"]["b1"]["project_id"] = "p2"
    assert PNL.project_of(po) == "p2"


def test_project_of_keeps_a_hand_tag_when_there_is_no_boq(client):
    po = {"id": "po2", "boq_id": "", "project_id": "p9"}
    assert PNL.project_of(po) == "p9"


def test_project_of_falls_back_when_the_boq_is_gone(client):
    """A deleted schedule must not make its documents vanish from every page."""
    po = {"id": "po3", "boq_id": "deleted-boq", "project_id": "p1"}
    assert PNL.project_of(po) == "p1"


def test_tax_invoice_follows_boq_then_proforma(client):
    _project()
    _chain()
    STORE["proformas"]["pi1"] = {"id": "pi1", "boq_id": "b1"}   # no project stored
    ti_via_pi = {"id": "t1", "proforma_id": "pi1", "boq_id": ""}
    ti_direct = {"id": "t2", "proforma_id": "", "boq_id": "b0", "project_id": ""}
    assert PNL.project_of(ti_via_pi, "invoice") == "p1"
    assert PNL.project_of(ti_direct, "invoice") == "p1"


def test_documents_raised_before_attach_appear_on_the_page(client):
    """The exact report: raise from the BOQ first, attach the BOQ later."""
    _project()
    _chain(pid="")                                   # BOQ on no project yet
    STORE["proformas"]["pi1"] = {"id": "pi1", "ref": "SF/PI/26-27/0007",
                                 "boq_id": "b1", "grand_total": 1000.0}
    STORE["purchases"]["po1"] = {"id": "po1", "ref": "SF/PO/26-27/0011",
                                 "boq_id": "b1", "project_id": "",
                                 "grand_total": 500.0, "vendor_name": "Sanghvi"}
    STORE["invoices"]["t1"] = {"id": "t1", "ref": "SF/TI/26-27/0003",
                               "boq_id": "b1", "proforma_id": "", "project_id": "",
                               "grand_total": 700.0}
    before = _page(client)
    for ref in ("SF/PI/26-27/0007", "SF/PO/26-27/0011", "SF/TI/26-27/0003"):
        assert ref not in before

    resp = client.post("/projects/view/p1", data={"action": "attach_boq", "boq_id": "b1"})
    assert resp.status_code == 302

    after = _page(client)
    for ref in ("SF/PI/26-27/0007", "SF/PO/26-27/0011", "SF/TI/26-27/0003"):
        assert ref in after, f"{ref} should follow its BOQ onto the project"

    # …and detaching takes them away again.
    client.post("/projects/view/p1", data={"action": "detach_boq", "boq_id": "b1"})
    gone = _page(client)
    for ref in ("SF/PI/26-27/0007", "SF/PO/26-27/0011", "SF/TI/26-27/0003"):
        assert ref not in gone


def test_raised_panel_lists_ra_bills_and_challans(client):
    _project()
    _chain()
    STORE["ra_bills"]["r1"] = {"id": "r1", "ref": "SF/RA/26-27/0001", "boq_id": "b0",
                               "leg": "supply", "status": "issued",
                               "date": "2026-10-05", "grand_total": 1180.0}
    STORE["delivery_challans"]["d1"] = {"id": "d1", "ref": "54", "boq_id": "b1",
                                        "date": "2026-10-11"}
    html = _page(client)
    seg = html.split("<h2>Raised from these BOQs</h2>", 1)[1].split("</table>", 1)[0]
    assert "SF/RA/26-27/0001" in seg, "an RA bill on an EARLIER revision still belongs"
    assert "Delivery challan" in seg and ">54<" in seg
    assert "Nothing raised" not in seg


def test_raised_panel_ignores_other_projects(client):
    _project()
    _chain()
    STORE["boqs"]["x0"] = {"id": "x0", "ref": "SF/BOQ/26-27/0099", "rev_no": 0,
                           "supersedes": "", "subtotal": 1.0, "project_id": "",
                           "line_items": []}
    STORE["ra_bills"]["r9"] = {"id": "r9", "ref": "SF/RA/26-27/0099", "boq_id": "x0",
                               "leg": "supply", "status": "issued"}
    html = _page(client)
    assert "SF/RA/26-27/0099" not in html


# =============================================================================
# THE P&L AND THE UNTAGGED LINE AGREE WITH THE PAGE
# =============================================================================

def test_po_from_boq_counts_on_project_and_not_as_untagged(client):
    _project()
    _chain()
    STORE["purchases"]["po1"] = {"id": "po1", "boq_id": "b1", "project_id": "",
                                 "status": "Issued", "subtotal": 400.0,
                                 "taxable_value": 400.0}
    untagged = PNL.untagged_cost(include_labour=False)
    assert untagged["po"]["count"] == 0, "it is on p1, so it is not untagged"
    po = PNL.project_pnl("p1", include_labour=False)["to_date"]["po"]
    assert po["count"] == 1 and po["amount"] == 400.0, "the PO's cost reaches p1's P&L"
    # Control: the same order on no project IS untagged.
    STORE["boqs"]["b1"]["project_id"] = ""
    STORE["boqs"]["b0"]["project_id"] = ""
    assert PNL.untagged_cost(include_labour=False)["po"]["count"] == 1


def test_tax_invoice_from_boq_reaches_the_pnl(client):
    """Before 28 Oct the P&L read tax invoices through a proforma only, so one
    raised straight from a BOQ was drawn on the page and missing from the P&L."""
    _project()
    _chain()
    STORE["invoices"]["t1"] = {"id": "t1", "boq_id": "b1", "proforma_id": "",
                               "subtotal": 900.0, "grand_total": 1062.0}
    ids = [tid for tid, _ in PNL._tax_invoices_of("p1")]
    assert ids == ["t1"]
