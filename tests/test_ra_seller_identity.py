"""
The seller block on the printed RA bill is read, never written into the source.

`print_ra()` carried two literals — a GSTIN beginning `03AAACS…` behind an
`or`, and the State `"Punjab (03)"` with nothing behind it at all. Both printed
on the face of a tax invoice, and both said the company supplies from a State it
has never traded in. The GSTIN one was the more dangerous of the two precisely
because it was a *fallback*: it only appeared once the real identity was
missing, which is the moment nobody is looking.

So these tests guard the shape of the fix rather than one page's output: there
is to be no State name and no GSTIN-shaped string anywhere in `ra.py`, and the
seller block is to read `branding` — which is where `/settings` puts the company
identity — the same way the bank block beneath it already does.
"""

import pathlib
import re

import pytest

import branding as B
import pipeline as P
from test_ra_record import boq_line, make_boq, make_bill, claim
from store import STORE

RA_SOURCE = (pathlib.Path(__file__).resolve().parent.parent / "ra.py").read_text(
    encoding="utf-8")

# 15 characters: State code, PAN, entity number, 'Z', checksum. The shape is
# fixed by the GST registration scheme, which is what makes it greppable.
_GSTIN_SHAPED = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")


def test_ra_py_carries_no_state_name_literal():
    """No Indian State is named anywhere in ra.py, in any context."""
    found = sorted(
        state for state in P.GST_STATE_CODES
        if re.search(rf"\b{re.escape(state)}\b", RA_SOURCE)
    )
    assert not found, (
        f"ra.py names {found} in its source. The seller's State is derived from "
        f"the company GSTIN via pipeline.gstin_state_label(); a State spelled "
        f"out here is a literal that will outlive whatever settings say.")


def test_ra_py_carries_no_gstin_literal():
    """No GSTIN-shaped string in ra.py — not as a value, not as a fallback."""
    found = sorted(set(_GSTIN_SHAPED.findall(RA_SOURCE)))
    assert not found, (
        f"ra.py carries the GSTIN literal(s) {found}. Party GSTINs come from "
        f"settings (seller) or the bill's own snapshot (buyer). A hardcoded one "
        f"behind an `or` prints exactly when the real one is missing.")


def test_seller_identity_is_read_from_branding_not_hardcoded():
    """The source-level half of the same rule, stated positively."""
    assert "B.COMPANY_GSTIN" in RA_SOURCE
    assert "P.gstin_state_label(" in RA_SOURCE
    assert "B.COMPANY_ADDR" in RA_SOURCE


@pytest.fixture()
def saved_identity():
    """Restore whatever identity the rest of the suite is running with."""
    before = B.current_settings()
    yield
    B.apply_settings(before)


@pytest.fixture()
def clean_store(client):
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()
    STORE["_boq_seeded"] = False
    yield STORE
    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


def _one_bill():
    make_boq("b1", [boq_line("1", 100, s_rate=100.0)])
    return make_bill("r1", "b1", 1, "supply", [claim("1", 10, rate=100.0)])


def test_printed_seller_block_follows_settings(client, clean_store, saved_identity):
    """Change the identity at /settings and the printed bill changes with it."""
    B.apply_settings({
        "COMPANY_GSTIN": "27AAAAA0000A1Z5",
        "COMPANY_ADDR":  "Unit 7, Ganesh Industrial Estate, Navi Mumbai - 400709",
    })
    rid = _one_bill()
    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)

    assert "27AAAAA0000A1Z5" in html
    assert "Maharashtra (27)" in html
    assert "Navi Mumbai - 400709" in html
    assert "Punjab" not in html


def test_printed_seller_block_prints_an_em_dash_when_settings_are_blank(
        client, clean_store, saved_identity):
    """
    A blank identity prints an em dash and stays blank.

    The whole point of removing the fallback: an unset GSTIN must be *visible*
    as unset, not quietly replaced by somebody else's registration.
    """
    B.apply_settings({"COMPANY_GSTIN": "", "COMPANY_ADDR": ""})
    rid = _one_bill()
    html = client.get(f"/ra/print/{rid}").get_data(as_text=True)

    seller = html.split("Billed By (Supplier)")[1].split("</div>")[1]
    assert "<b>GSTIN:</b> &mdash;" in seller
    assert "<b>State:</b> &mdash;" in seller
    assert not _GSTIN_SHAPED.search(seller)
