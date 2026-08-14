"""
The BOQ page is the way in to RA billing.

The prefill was never the missing piece — `/ra/create?boq=<id>&leg=<leg>` has
always built the full claim grid from the schedule, and there is no blank RA
entry form in this app. What was missing was any way to *reach* it from the
schedule you were looking at: `boq.py` linked out to RA bills that already
existed and to nothing that would start one.

Three properties, and the middle one is the one worth having:

- the control is there on the tip of a revision chain;
- **it is NOT there on a superseded revision** — the route it points at also
  now refuses a stale BOQ (redirecting with an error), so both the UI and the
  route enforce that claims can only be raised against the latest revision;
- following it lands on the prefilled grid for the right BOQ *and the right
  leg*, so the two buttons are not two spellings of one.

Scope note: this is a link. `/ra/create`, `_entry_form` and `_claim_rows` are
untouched, and nothing here asserts anything about how the grid is built —
that is `test_ra_routes.py`'s.
"""

import pytest

from store import STORE

from test_boq_revisions import _mkboq, _mkbill, clean  # noqa: F401


# ── The control, and where it is allowed to appear ──────────────────────────

def test_the_view_page_offers_an_ra_bill_on_the_tip_of_a_chain(client, clean):
    _mkboq("rev0", rev=0)

    html = client.get("/boq/view/rev0").get_data(as_text=True)

    assert "/ra/create?boq=rev0&leg=supply" in html
    assert "/ra/create?boq=rev0&leg=installation" in html


def test_a_superseded_revision_offers_no_way_to_start_a_bill(client, clean):
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    old = client.get("/boq/view/rev0").get_data(as_text=True)

    # Not "no link to rev0" — no link to /ra/create at all. A control pointing
    # at the tip from the superseded page would be worse than none: it would
    # read as billing the schedule on screen.
    assert "/ra/create" not in old
    # The page still says why, because `Revise` is suppressed by the same
    # predicate and names what replaced it.
    assert "Revised by SF/BOQ/26-27/0002" in old


def test_the_tip_of_that_same_chain_still_offers_it(client, clean):
    """The control is gated on being superseded, not on having a predecessor."""
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    tip = client.get("/boq/view/rev1").get_data(as_text=True)

    assert "/ra/create?boq=rev1&leg=supply" in tip
    assert "boq=rev0" not in tip


def test_one_predicate_drives_both_controls(client, clean):
    """
    `Revise` and the RA links agree on every record, in both directions.

    They are separate features that answer the same question, and a page
    offering to bill a schedule it will not let you revise is incoherent.
    """
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    for bid in ("rev0", "rev1"):
        html = client.get(f"/boq/view/{bid}").get_data(as_text=True)
        assert (f"revise={bid}" in html) == ("/ra/create" in html)


# ── Following it ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("leg", ["supply", "installation"])
def test_following_the_control_lands_on_a_prefilled_grid_for_that_boq(
        client, clean, leg):
    _mkboq("rev0", rev=0)

    page = client.get(f"/ra/create?boq=rev0&leg={leg}")
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    # The picker is what you get when the route cannot tell which BOQ you
    # mean. Landing on it would mean the parameters did not carry.
    assert "Which schedule is this a claim against?" not in html
    # The schedule's own line, and the id the claim will be matched on.
    assert "aaaaaaaaaaaa" in html
    assert "Line 1" in html
    assert "Sify Bangalore" in html
    # Posting goes back to the same BOQ and leg, not to a re-picked one.
    assert f'action="/ra/create?boq=rev0&leg={leg}"' in html


@pytest.mark.parametrize("leg,own_rate,other_rate",
                         [("supply", "100", "50"), ("installation", "50", "100")])
def test_the_two_buttons_are_not_two_spellings_of_one(client, clean, leg,
                                                      own_rate, other_rate):
    """
    The leg reaches the grid, and it is the leg that decides the rate.

    `_line()` prices supply at 100 and installation at 50, so asserting the
    OTHER leg's rate is absent is what makes this a discriminator rather than
    a presence check — a grid that ignored the parameter would show one of
    them on both pages. The approved quantity is also 100 and would muddy
    that, except it renders as `data-approved`, never as a `value`.
    """
    _mkboq("rev0", rev=0)

    html = client.get(f"/ra/create?boq=rev0&leg={leg}").get_data(as_text=True)

    assert f'value="{leg}"' in html              # the disabled leg field
    assert f'data-rate="{own_rate}"' in html     # the rate carried onto the row
    assert f'value="{own_rate}"' in html
    assert f'value="{other_rate}"' not in html   # …and the other leg's is not


def test_the_grid_reached_this_way_still_knows_what_is_already_claimed(
        client, clean):
    """
    Arriving from the BOQ page is the same entry as arriving from the picker.

    The claimed-to-date column is the whole point of an RA grid, and it is a
    live figure summed across the chain — so the one thing worth proving about
    the link is that it lands somewhere that has it, not on a blank form.
    """
    _mkboq("rev0", rev=0)
    _mkbill("bill1", "rev0", 1, claims=[{
        "line_id": "aaaaaaaaaaaa", "item_no": "1", "description": "Line 1",
        "unit": "Mtrs", "approved_qty": 100.0, "approved_rate": 100.0,
        "prev_qty": 0.0, "qty": 40.0, "rate": 100.0, "amount": 4000.0,
        "balance_qty": 60.0, "rate_varies": False,
        "hsn_sac": "73063090", "gst_rate": 18.0,
    }])

    html = client.get("/ra/create?boq=rev0&leg=supply").get_data(as_text=True)

    assert "RA2" in html            # the number is assigned, not typed
    assert "60" in html             # the balance left on that line


def test_ra_route_rejects_superseded_boq(client, clean):
    _mkboq("rev0", rev=0)
    _mkboq("rev1", rev=1, supersedes="rev0")

    # The tip is accepted
    res = client.get("/ra/create?boq=rev1&leg=supply")
    assert res.status_code == 200

    # The superseded revision is rejected with a redirect
    res = client.get("/ra/create?boq=rev0&leg=supply")
    assert res.status_code == 302
    assert "/ra/create" in res.headers["Location"]
    assert "superseded" in res.headers["Location"]
