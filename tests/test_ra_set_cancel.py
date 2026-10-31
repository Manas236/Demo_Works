"""
A Supply + Installation set is cancelled TOGETHER — both legs and the merged
tax invoice, with one required reason — and never one leg alone.

31 October 2026, CLIENT_CHANGES.md §0 sixty-third block, Part D. Also the
one-click "Supply + Installation together" toggle on `/ra/create`.
"""

import re

import pytest

import address
import demo_data as DD
import merged_ra as MRA
import ra as RA
from store import STORE


@pytest.fixture()
def sched(client):
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()
    client.get("/boq/")
    client.get("/settings/")
    address.ensure_demo_addresses()
    yield DD.BOQ_META["id"]
    for k in ("ra_bills", "merged_ras", "measurements", "delivery_challans"):
        STORE.setdefault(k, {}).clear()


def _both(client, bid, qty="1.5"):
    """Raise a set at `/raboth/create`; `(merged, [supply leg, install leg])`."""
    before = set(STORE["merged_ras"])
    html = client.get(f"/raboth/create?boq={bid}").get_data(as_text=True)
    flat = " ".join(html.split())
    data = {"boq": bid, "date": "2026-10-31"}
    for leg in ("supply", "installation"):
        lid, rate = re.findall(
            r'name="%s_qty_([0-9a-f]{12})"[^>]*?/>.*?name="%s_rate_\1" value="([^"]*)"'
            % (leg, leg), flat)[0]
        data[f"{leg}_qty_{lid}"] = qty
        data[f"{leg}_rate_{lid}"] = rate
    r = client.post(f"/raboth/create?boq={bid}", data=data)
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:600]
    (mid,) = set(STORE["merged_ras"]) - before
    m = STORE["merged_ras"][mid]
    legs = [STORE["ra_bills"][m["supply_ra_id"]], STORE["ra_bills"][m["installation_ra_id"]]]
    return m, legs


def test_the_ra_form_offers_both_legs_together_in_one_click(client, sched):
    html = client.get(f"/ra/create?boq={sched}&leg=supply").get_data(as_text=True)
    assert f'href="/raboth/create?boq={sched}"' in html
    assert "Supply + Installation together" in html


def test_cancelling_a_leg_sends_you_to_the_set_and_cancels_nothing_alone(client, sched):
    m, legs = _both(client, sched)
    leg = legs[0]
    for verb in ("get", "post"):
        r = getattr(client, verb)(f"/ra/cancel/{leg['id']}",
                                  data={"cancel_reason": "just this one"})
        assert r.status_code == 302
        assert f"/merged/cancel/{m['id']}" in r.headers["Location"]
    assert not any(RA.is_cancelled(b) for b in legs), "a single leg was cancelled"
    assert not MRA.is_cancelled(m)
    # …and the guard underneath: a single-leg cancel is refused outright.
    assert RA.can_cancel(leg)[0] is False


def test_the_leg_view_names_what_its_cancel_does(client, sched):
    _m, legs = _both(client, sched)
    html = client.get(f"/ra/view/{legs[1]['id']}").get_data(as_text=True)
    assert "Cancel both legs &amp; the tax invoice" in html


def test_the_set_cancel_needs_one_reason_and_takes_all_three(client, sched):
    m, legs = _both(client, sched)
    r = client.post(f"/merged/cancel/{m['id']}", data={"reason": "  "})
    assert "type=error" in r.headers["Location"]
    assert not MRA.is_cancelled(m) and not any(RA.is_cancelled(b) for b in legs)
    client.post(f"/merged/cancel/{m['id']}", data={"reason": "remeasured"})
    assert MRA.is_cancelled(m) and all(RA.is_cancelled(b) for b in legs)
    assert all("remeasured" in RA.cancelled_reason(b) for b in legs)


def test_the_cancelled_set_invoice_keeps_its_number_under_the_overprint(client, sched):
    m, _legs = _both(client, sched)
    ref = m["tax_invoice_ref"]
    client.post(f"/merged/cancel/{m['id']}", data={"reason": "remeasured"})
    html = client.get(f"/merged/print/{m['id']}").get_data(as_text=True)
    assert "CANCELLED" in html and ref in html
    m2, _ = _both(client, sched, qty="1")
    assert m2["tax_invoice_ref"] != ref, "a GST serial was reissued"
