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
