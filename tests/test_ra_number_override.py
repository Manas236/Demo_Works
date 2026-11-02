"""
The RA number typed by hand, forward only PER BOQ — CLIENT_CHANGES.md §0
sixty-fourth block, Part 3 (31 Oct 2026).

Proved: a typed RA number above the chain's highest is accepted; at or below
it is refused naming the highest; afterwards the automatic series carries on
above it, so RA numbers stay UNIQUE and INCREASING per BOQ; a deleted bill's
number stays spent; and the over-claim guard is unaffected.
"""

import json

import pytest

import docnum as DN
import ra as RA
from store import STORE
from tests.test_ra_both_oct28 import _approved, sched  # noqa: F401 — the fixture


@pytest.fixture(autouse=True)
def _no_ledger():
    """The RA-number ledger lives in `settings`, which outlives a test."""
    def clear():
        rec = (STORE.get("settings") or {}).get(DN.HIGHWATER_RECORD)
        if isinstance(rec, dict):
            rec.pop(DN.RA_NO, None)
    clear()
    yield
    clear()


def _raise(client, bid, qty="1", **over):
    lid, _q = _approved(bid, "supply")[0]
    data = {"date": "2026-10-30",
            "ra_json": json.dumps({"lines": [{"line_id": lid, "qty": qty, "rate": "1"}]})}
    data.update(over)
    return client.post(f"/ra/create?boq={bid}&leg=supply", data=data)


def _nos():
    return sorted(int(b["ra_no"]) for b in STORE["ra_bills"].values())


def test_the_form_prefills_the_next_ra_number(client, sched):
    html = client.get(f"/ra/create?boq={sched}&leg=supply").get_data(as_text=True)
    assert 'name="ra_no_typed"' in html and 'value="1"' in html


def test_forward_is_accepted_and_the_series_carries_on_above_it(client, sched):
    assert _raise(client, sched).status_code == 302                  # RA1
    assert _raise(client, sched, ra_no_typed="5").status_code == 302  # RA5
    assert _raise(client, sched).status_code == 302                  # RA6, automatic
    assert _nos() == [1, 5, 6]
    assert len(set(_nos())) == len(_nos())


def test_at_or_below_the_highest_is_refused_and_names_it(client, sched):
    _raise(client, sched, ra_no_typed="4")
    for typed in ("4", "2"):
        r = _raise(client, sched, ra_no_typed=typed)
        assert r.status_code == 200
        assert "the highest already used on this schedule is RA4" in r.get_data(as_text=True)
    assert _nos() == [4]


def test_a_deleted_bills_number_stays_spent(client, sched):
    _raise(client, sched, ra_no_typed="7")
    rid = next(iter(STORE["ra_bills"]))
    STORE["ra_bills"].pop(rid)
    r = _raise(client, sched, ra_no_typed="7")
    assert r.status_code == 200 and "RA7" in r.get_data(as_text=True)
    assert DN.ra_no_highest(RA._chain_key(sched), 0) == 7


def test_the_over_claim_guard_is_unaffected_by_a_typed_number(client, sched):
    lid, approved_qty = _approved(sched, "supply")[0]
    assert _raise(client, sched, qty=str(approved_qty), ra_no_typed="9").status_code == 302
    r = _raise(client, sched, qty="1", ra_no_typed="12")
    assert r.status_code == 200, "the over-claim block must still refuse"
    assert _nos() == [9]
    assert RA.claimed_by_line(sched).get(lid, {}).get("supply", approved_qty) is not None


def test_without_the_permission_a_changed_number_is_refused(client, sched, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "has_perm", lambda p: p != "docnum.override")
    r = _raise(client, sched, ra_no_typed="5")
    assert r.status_code == 200 and "permission" in r.get_data(as_text=True)
    assert not STORE["ra_bills"]
