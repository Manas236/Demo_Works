"""
The BOQ's in-place edit — 2 November 2026, CLIENT_CHANGES.md §0 block of that
date, Part 2 (ABOUT.md §7 gap 105 closed); lock 2.

`/boq/edit/<id>` is `/boq/create`'s form prefilled and saved ONTO the record:
lines added / removed / moved / every column (base, escalation, discount
included), sections, the party, the terms, the round-off tick and the root's
number (forward only). A line claimed on any RA bill of the chain cannot be
deleted, nor its quantity cut below the live claim. Every edit is logged with
the screen-only band; the print carries none.
"""

import json

import pytest

import boq as BQ
from store import STORE
from test_boq import FORM


def _boq(client):
    r = client.post("/boq/create", data=FORM)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return next(b for b in STORE["boqs"].values() if b.get("date") == FORM["date"])


def _post(client, boq, mutate=None, **over):
    """The edit form's POST, built from the form's own prefill — an untouched
    submit is exactly this; `mutate(boot)` changes the editor's model."""
    boot, prefill = BQ._edit_prefill(boq)
    if mutate:
        mutate(boot)
    data = {k: v for k, v in prefill.items() if v is not None}
    data["boq_json"] = json.dumps(boot)
    data["round_off_present"] = "1"
    data.update(over)
    return client.post(f"/boq/edit/{boq['id']}", data=data)


def _priced(boot):
    return [l for l in boot["lines"] if not l["is_header"]]


def _set_qty(line, q):
    """A line's quantity — through its area boxes when the section has areas
    (the editor derives `total_qty` from them), else the box itself."""
    if line.get("area_qty"):
        keys = list(line["area_qty"])
        line["area_qty"] = {k: (str(q) if i == 0 else "") for i, k in enumerate(keys)}
    else:
        line["total_qty"] = str(q)


@pytest.fixture()
def boq(client):
    STORE.setdefault("ra_bills", {}).clear()
    yield _boq(client)
    STORE["ra_bills"].clear()


def test_the_edit_form_is_the_create_form_prefilled(client, boq):
    html = client.get(f"/boq/edit/{boq['id']}").get_data(as_text=True)
    assert f'action="/boq/edit/{boq["id"]}"' in html and "Save changes" in html
    assert 'name="doc_no_seq"' in html and 'id="boq_json"' in html
    assert boq["line_items"][0]["description"][:30] in html


def test_every_line_operation_and_the_party_print(client, boq):
    first, second = _priced(BQ._edit_prefill(boq)[0])[:2]

    def mutate(boot):
        lines = boot["lines"]
        a = next(l for l in lines if l["line_id"] == first["line_id"])
        _set_qty(a, 77)
        a.update({"description": "Edited description",
                  "supply_base_rate": "250", "supply_escalation_pct": "10",
                  "supply_disc_pct": "5", "unit": "Mtr"})
        lines.remove(next(l for l in lines if l["line_id"] == second["line_id"]))
        lines.remove(a)
        lines.append(a)                                   # moved to the end
        new = dict(a, line_id="", item_no="99", description="A brand new line")
        _set_qty(new, 3)
        lines.append(new)
    r = _post(client, boq, mutate, account_name="New Customer Pvt Ltd",
              payment_terms="30 days credit")
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    descs = [l["description"] for l in boq["line_items"]]
    assert "A brand new line" in descs and descs[-2] == "Edited description"
    assert second["line_id"] not in {l["line_id"] for l in boq["line_items"]}
    edited = next(l for l in boq["line_items"] if l["line_id"] == first["line_id"])
    assert (edited["total_qty"], edited["supply_base_rate"], edited["supply_escalation_pct"],
            edited["supply_disc_pct"], edited["unit"]) == (77.0, 250.0, 10.0, 5.0, "Mtr")
    assert boq["account_name"] == "New Customer Pvt Ltd"
    html = client.get(f"/boq/view/{boq['id']}").get_data(as_text=True)
    for needle in ("Edited description", "A brand new line", "New Customer Pvt Ltd",
                   "30 days credit", "Edited after issue"):
        assert needle in html, needle
    assert "@media print { .el-band { display:none !important; } }" in html


def test_a_claimed_line_cannot_be_deleted_or_cut_below_its_claim(client, boq):
    line = _priced(BQ._edit_prefill(boq)[0])[0]
    STORE["ra_bills"]["rb"] = {"id": "rb", "boq_id": boq["id"], "ra_no": 1,
                               "status": "issued",
                               "claims": [{"line_id": line["line_id"], "qty": 2.0}]}
    before = json.dumps(boq["line_items"], sort_keys=True)
    r = _post(client, boq, lambda b: b["lines"].remove(
        next(l for l in b["lines"] if l["line_id"] == line["line_id"])))
    assert r.status_code == 200 and "already been claimed" in r.get_data(as_text=True)
    r = _post(client, boq, lambda b: _set_qty(next(
        l for l in b["lines"] if l["line_id"] == line["line_id"]), 1))
    assert r.status_code == 200 and "cannot go below 2" in r.get_data(as_text=True)
    assert json.dumps(boq["line_items"], sort_keys=True) == before
    # At the claim, or above it, is fine; so is every other column.
    def at_claim(b):
        li = next(l for l in b["lines"] if l["line_id"] == line["line_id"])
        _set_qty(li, 2)
        li["description"] = "Still claimed, renamed"
    r = _post(client, boq, at_claim)
    assert r.status_code == 302, r.get_data(as_text=True)[:800]


def test_a_cancelled_bills_claim_does_not_floor_the_quantity(client, boq):
    line = _priced(BQ._edit_prefill(boq)[0])[0]
    STORE["ra_bills"]["rb"] = {"id": "rb", "boq_id": boq["id"], "ra_no": 1,
                               "status": "cancelled",
                               "claims": [{"line_id": line["line_id"], "qty": 5.0}]}
    r = _post(client, boq, lambda b: _set_qty(next(
        l for l in b["lines"] if l["line_id"] == line["line_id"]), 1))
    assert r.status_code == 302, r.get_data(as_text=True)[:800]


def test_the_root_number_moves_forward_only_and_revisions_follow(client, boq):
    rev = client.post(f"/boq/create", data=dict(FORM, rev_no="1", supersedes=boq["id"]))
    assert rev.status_code == 302
    child = next(b for b in STORE["boqs"].values() if b.get("supersedes") == boq["id"])
    assert child["ref"] == boq["ref"] + "/1"
    r = _post(client, boq, doc_no_seq="0")
    assert r.status_code == 200
    r = _post(client, boq, doc_no_seq="0060")
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    assert boq["ref"].endswith("/0060") and child["ref"] == boq["ref"] + "/1"
    assert boq["number_override"]["to"] == boq["ref"]


def test_an_unchanged_save_moves_nothing_on_the_print(client, boq):
    before = client.get(f"/boq/print/{boq['id']}").get_data(as_text=True)
    r = _post(client, boq)
    assert r.status_code == 302 and "Nothing+changed" in r.headers["Location"]
    assert client.get(f"/boq/print/{boq['id']}").get_data(as_text=True) == before
