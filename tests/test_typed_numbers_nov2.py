"""
Typed numbers on the BOQ root and the merged tax invoice — 2 November 2026,
CLIENT_CHANGES.md §0 block of that date, Part 4 (ABOUT.md §7 gap 104, closed
for these two). Forward only, through `docnum.validate()`; refused at or
below the highest used, naming it; the series carries on above a typed one.
"""

import docnum as DN
import merged_ra as MRA
from store import STORE
from test_boq import FORM
from test_merged_ra import chain, pair  # noqa: F401


# ── The BOQ root ────────────────────────────────────────────────────────────

def _boqs():
    return sorted(b["ref"] for b in STORE["boqs"].values()
                  if b.get("date") == FORM["date"])


def test_the_boq_create_form_draws_the_root_number(client):
    html = client.get("/boq/create").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html and "BOQ No." in html


def test_a_typed_boq_root_is_saved_and_the_series_carries_on(client):
    r = client.post("/boq/create", data=dict(FORM, doc_no_seq="0040"))
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    typed = next(b for b in STORE["boqs"].values() if b["ref"].endswith("/0040"))
    assert typed["number_override"]["to"] == typed["ref"]
    r = client.post("/boq/create", data=FORM)
    assert r.status_code == 302
    assert any(b["ref"].endswith("/0041") for b in STORE["boqs"].values())


def test_a_boq_root_at_or_below_the_highest_is_refused(client):
    client.post("/boq/create", data=dict(FORM, doc_no_seq="0040"))
    before = len(STORE["boqs"])
    r = client.post("/boq/create", data=dict(FORM, doc_no_seq="0039"))
    assert r.status_code == 200
    assert "highest already used in this series is 0040" in r.get_data(as_text=True)
    assert len(STORE["boqs"]) == before


def test_a_revision_draws_no_number_box(client):
    client.post("/boq/create", data=FORM)
    bid = next(b["id"] for b in STORE["boqs"].values() if b.get("date") == FORM["date"])
    html = client.get(f"/boq/create?revise={bid}").get_data(as_text=True)
    assert "BOQ No." not in html


# ── The merged tax invoice ─────────────────────────────────────────────────

def test_the_merged_form_draws_the_tax_invoice_number(client, pair):
    chain_, _s, _i = pair
    html = client.get(f"/merged/create?boq={chain_['boq_id']}").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html and "Tax Invoice No." in html


def test_a_typed_merged_number_is_used_and_forward_only(client, pair):
    chain_, s, i = pair
    data = {"boq_id": chain_["boq_id"], "supply_ra_id": s["id"],
            "installation_ra_id": i["id"], "notes": "", "doc_no_seq": "0001"}
    # 0001 is the default here; anything at or below a used TI ordinal is refused.
    STORE["invoices"]["x"] = {"id": "x", "ref": "SF/TI/26-27/0030", "fy": "26-27"}
    fy = MRA.P.fy_of(MRA._now_date())
    STORE["invoices"]["x"]["ref"] = f"SF/TI/{fy}/0030"
    STORE["invoices"]["x"]["fy"] = fy
    r = client.post("/merged/create", data=dict(data, doc_no_seq="0020"))
    assert r.status_code == 200 and "0030" in r.get_data(as_text=True)
    assert not STORE["merged_ras"]
    r = client.post("/merged/create", data=dict(data, doc_no_seq="0045"))
    assert r.status_code == 302, r.get_data(as_text=True)[:1200]
    doc = next(iter(STORE["merged_ras"].values()))
    assert doc["tax_invoice_ref"].endswith("/0045")
    assert doc["number_override"]["to"] == doc["tax_invoice_ref"]
    assert DN.highest_used(DN.TI, fy) == 45
    STORE["invoices"].pop("x", None)


def test_the_merged_number_is_still_locked_on_edit(client, pair):
    chain_, s, i = pair
    doc, err = MRA.create(s, i)
    assert not err
    html = client.get(f"/merged/edit/{doc['id']}").get_data(as_text=True)
    assert 'name="doc_no_seq"' not in html, "lock 5: a tax invoice's number"
