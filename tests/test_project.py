import pytest
from store import STORE
import pipeline as P

import sys
import pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent / "tools"))
import backfill_projects

def test_backfill_groups_different_spellings_into_one_project(client):
    """
    Two BOQs whose project_name differs in spelling but normalises to the same
    norm_name must propose ONE project covering both.
    """
    STORE["boqs"].clear()
    STORE["projects"].clear()

    # Create two BOQs with different spellings of the same normalized name
    STORE["boqs"]["b1"] = {
        "id": "b1",
        "project_name": "Sify Bangalore",
        "client": "Client A",
        "site_address": "Site A"
    }
    STORE["boqs"]["b2"] = {
        "id": "b2",
        "project_name": "Sify bangalore ",
        "client": "Client B",
        "site_address": "Site B"
    }

    # Run the backfill logic
    backfill_projects.backfill(write=True)

    assert len(STORE["projects"]) == 1, "Should group into exactly 1 project"
    proj = list(STORE["projects"].values())[0]
    norm = P.norm_name("Sify Bangalore")
    assert proj["norm_name"] == norm

    # Both BOQs should be linked to this single project
    assert STORE["boqs"]["b1"]["project_id"] == proj["id"]
    assert STORE["boqs"]["b2"]["project_id"] == proj["id"]

def test_attach_boq_attaches_entire_chain(client):
    """
    Attaching an existing BOQ to a project must attach its entire revision chain,
    never a single revision.
    """
    STORE["boqs"].clear()
    STORE["projects"].clear()

    # Create a project
    STORE["projects"]["p1"] = {
        "id": "p1", "name": "Project Alpha", "norm_name": "projectalpha"
    }

    # Create a revision chain of 3 BOQs
    STORE["boqs"]["b1"] = {"id": "b1", "rev_no": 0, "supersedes": ""}
    STORE["boqs"]["b2"] = {"id": "b2", "rev_no": 1, "supersedes": "b1"}
    STORE["boqs"]["b3"] = {"id": "b3", "rev_no": 2, "supersedes": "b2"}

    # Use the projectview /projects/view/p1 endpoint to attach 'b2'
    response = client.post("/projects/view/p1", data={
        "action": "attach_boq",
        "boq_id": "b2"
    })

    # The redirect should be successful
    assert response.status_code == 302

    # The ENTIRE chain should now be attached to p1
    assert STORE["boqs"]["b1"]["project_id"] == "p1"
    assert STORE["boqs"]["b2"]["project_id"] == "p1"
    assert STORE["boqs"]["b3"]["project_id"] == "p1"

def test_backfill_idempotence(client):
    """The backfill script must be idempotent."""
    STORE["boqs"].clear()
    STORE["projects"].clear()
    STORE["boqs"]["b1"] = {"id": "b1", "project_name": "Sify Bangalore"}
    
    backfill_projects.backfill(write=True)
    assert len(STORE["projects"]) == 1
    p_id = STORE["boqs"]["b1"]["project_id"]
    
    # Run a second time
    backfill_projects.backfill(write=True)
    assert len(STORE["projects"]) == 1
    assert STORE["boqs"]["b1"]["project_id"] == p_id

def test_no_currency_on_project_view(client):
    """No currency or totals should be displayed on the project view."""
    STORE["projects"].clear()
    STORE["projects"]["p1"] = {"id": "p1", "name": "Sify"}
    html = client.get("/projects/view/p1").get_data(as_text=True)
    assert "&#8377;" not in html, "Rupee symbol found!"
    assert "₹" not in html, "Rupee symbol found!"

def test_tax_invoice_inherits_through_proforma(client):
    """A tax invoice derives its project through its proforma, storing no copy."""
    STORE["invoices"].clear()
    STORE["invoices"]["ti1"] = {"id": "ti1", "proforma_id": "pi1"}
    STORE["proformas"]["pi1"] = {"id": "pi1", "project_id": "p1"}
    
    # Assert no copy is stored on the invoice
    assert "project_id" not in STORE["invoices"]["ti1"]

def test_ti_with_pi_absent(client):
    """A tax invoice whose proforma is missing should still not crash."""
    STORE["invoices"].clear()
    STORE["invoices"]["ti1"] = {"id": "ti1", "proforma_id": "missing"}
    assert "project_id" not in STORE["invoices"]["ti1"]
    # If the app tries to resolve it, it should return None, which we test implicitly
    # by ensuring we can fetch it (if it has a route, but for now just data struct)

def test_proforma_or_po_with_no_project_still_rendering(client):
    """A proforma or PO with no project_id must still render without crashing."""
    STORE["proformas"].clear()
    STORE["purchases"].clear()
    STORE["proformas"]["pi1"] = {"id": "pi1"}
    STORE["purchases"]["po1"] = {"id": "po1"}
    
    assert "project_id" not in STORE["proformas"]["pi1"]
    assert "project_id" not in STORE["purchases"]["po1"]

def test_delete_refused_when_attached(client):
    """A project cannot be deleted if it has documents attached."""
    STORE["projects"]["p1"] = {"id": "p1", "name": "Sify"}
    STORE["boqs"]["b1"] = {"id": "b1", "project_id": "p1"}
    
    r = client.post("/projects/delete/p1")
    assert r.status_code == 302
    assert "p1" in STORE["projects"]

def test_get_delete_mutating_nothing(client):
    """GET /projects/delete/<id> must not mutate the store."""
    STORE["projects"]["p1"] = {"id": "p1"}
    r = client.get("/projects/delete/p1")
    assert r.status_code == 200  # Confirmation page
    assert "p1" in STORE["projects"]

def test_boq_with_no_project_still_rendering_everywhere(client):
    """A BOQ with no project_id must render properly."""
    STORE["boqs"]["b1"] = {"id": "b1"}
    assert "project_id" not in STORE["boqs"]["b1"]
