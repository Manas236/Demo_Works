"""
dcbill.py — is this delivery challan billed, and by which RA bill?
==================================================================
CLIENT_CHANGES.md §0, fortieth block (4 October 2026), ruling **C**: a challan
is *billed* when any **non-cancelled** RA bill lists it in `source_dc_ids`, and
a billed challan is marked on its own pages and blocked from a second bill.

**This module is the one place that question is answered.** Two modules need
the answer and may not import each other:

    ra.py       — leaves a billed challan out of the picker on `/ra/create`
                  and refuses a POST that names one
    challan.py  — says *Billed in <RA ref>* on `/dc/view` and the register

`challan -> ra` is the load-bearing prohibition of ABOUT.md §5 `/dc` and
`ra -> challan` is refused from the other side (§2j). The repository's usual
one-way trick — read the other collection out of `STORE` directly — would have
given `challan.py` its OWN copy of "which bills count", beside the one `ra.py`
needs: two near-identical predicates in two modules, which is exactly ABOUT.md
§7 gap 16b's failure. So the predicate lives here, in a leaf both import, and
neither defines one of its own (`tests/test_ra_from_source.py` holds that).

**Derived, never stored.** Nothing on a challan record says it is billed.
Cancelling the RA bill frees the challan with no write to the challan at all,
and deleting a draft bill does the same — the answer is read off the bills
every time, exactly as `ra.claimed_by_line()` and
`challan.dispatched_by_line()` are.

**Absent means manual.** A bill written before 4 October 2026, or raised
through the manual path since, carries no `source_dc_ids` key. That is a
WRITTEN meaning — such a bill names no challan — and it is never inferred
from the bill's leg, its chain or its claim rows. Nothing is backfilled.

Import direction — a LEAF
-------------------------
Imports `store` and nothing else, `series.py`'s standard: no `ra`, no
`challan`, no `boq`, no `flask`, no `auth`. `tests/test_import_directions.py`
holds it as a whitelist.
"""

from store import STORE

# The key an RA bill carries when it was raised FROM challans — a list of
# challan ids, written ONCE by `ra.create_ra()` and never edited afterwards.
# Named here because this module is its only reader; `ra.py` writes through
# the constant, so the spelling exists in one place.
SOURCE_KEY = "source_dc_ids"


def bill_is_live(bill) -> bool:
    """
    Does this RA bill still bill what it names? True unless it is cancelled.

    ⚠ **A raw status test, because `ra.py` imports this module and so this
    module may not call `ra.is_cancelled()`.** It agrees with it exactly:
    `ra.status_of()` lower-cases and strips the field and reads anything it
    does not recognise as `issued`, so a bill is cancelled precisely when the
    normalised field is `"cancelled"` — which is this test.
    `tests/test_ra_from_source.py` holds the two together over every status
    value rather than leaving it to this comment — `approval.can_print()`'s
    arrangement with the same function.

    A **draft** bill counts, for `claimed_by_line()`'s reason: it is not yet a
    document, but two drafts naming one challan would otherwise both pass.
    """
    return str((bill or {}).get("status") or "").strip().lower() != "cancelled"


def _ra_no(bill) -> int:
    try:
        return int((bill or {}).get("ra_no") or 0)
    except (TypeError, ValueError):
        return 0


def billing_index() -> dict:
    """
    `{challan id: (ra id, bill)}` for every challan a live RA bill names.

    The single walk. `billed_by()` is this, for one id — there is no second
    traversal to drift from it.

    Where two live bills name the same challan — unreachable through
    `/ra/create`, which refuses the second, but possible in a hand-edited or
    restored record — the **lowest `ra_no`** answers, ties broken by id, so
    the answer is at least the same every time it is asked.
    """
    out = {}
    bills = sorted((STORE.get("ra_bills") or {}).items(),
                   key=lambda kv: (_ra_no(kv[1]), str(kv[0])))
    for rid, bill in bills:
        if not bill_is_live(bill):
            continue                      # cancelled — it frees what it named
        ids = bill.get(SOURCE_KEY)
        if not isinstance(ids, list):
            continue                      # absent: a manual / pre-feature bill
        for dc_id in ids:
            key = str(dc_id or "")
            if key and key not in out:
                out[key] = (rid, bill)
    return out


def billed_by(dc_id):
    """`(ra id, bill)` of the live RA bill this challan is billed in, or None."""
    return billing_index().get(str(dc_id or ""))
