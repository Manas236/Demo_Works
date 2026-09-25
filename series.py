"""
series.py — the document-number FLOOR, and one scan per series
===============================================================

ABOUT.md §7 gap 36: *"Eight of the ten document number series cannot be set to
a starting number, so a go-live restarts them at 0001 beside the client's
running paper book."* This module is what closes that, and
CLIENT_CHANGES.md §0's thirty-first block (25 September 2026) is the
authorisation.

## The rule, in one line

    next = max(existing max in the current numbering scope + 1, floor)

**A floor only ever moves a series FORWARD.** It is not a counter and it is not
a next-number: it is a lower bound the minter is held to. That distinction is
what makes it safe to set on a live box — a floor below where the series has
already reached does nothing at all, and the POST refuses one rather than
letting an operator believe it did something.

**A blank floor is today's behaviour, byte-identical.** `max(highest + 1, 0)`
is `highest + 1`. Every golden in the suite is written against a store with no
floors set, and none of them moved.

## Why a LEAF, and not `settings.py`

The floors are stored in a **settings record** — `STORE["settings"]
["document_series_floors"]`, its own key, exactly as the draft-PO series
(`po_draft_series`), the challan series (`delivery_challan_series`) and the
labour cost (`labour_cost`) are. That is deliberate and it is not decoration:
`branding.apply_settings()` must not push these onto the letterhead, and above
all **the nav's amber completeness dot must not count a blank floor as a
missing statutory detail**. That dot means "a document will print an amber
chip"; a starting number is not one, and a blank floor is the *normal*
configuration.

But the **accessor** cannot live in `settings.py`, and this is the constraint
that decided the shape: **`boq.py` may not import `settings.py`** — the arrow
is refused in `tests/test_import_directions.py` with the reason *"settings
imports quotation; nothing downstream of it may import back"*. `charge.py`,
`docsheet.py`, `boqpick.py`, `employee.py`, `project.py` and `chrome.py` are
refused the same arrow. So a floor read through `settings.py` would have been
reachable from some minters and not from others.

This module therefore imports **`store` and nothing else** — `demo_data.py`'s
position in the graph — and reads `STORE["settings"]` directly. That is the
one-way trick this repository already runs between quotation/proforma,
proforma/invoice, boq/ra, ra/receipt and boq/challan, used once more:
`settings.py` owns the *page* that edits the record, this module owns the
*rule* the record expresses, and neither imports the other.

## Why the SCAN lives here too, and not in each minter

Each minter used to carry its own `for … max(…)` loop. The floor needs two
readers of the same question — the minter, which mints, and `/settings`, which
has to say *"that is at or below the current max, which is N"* — and **two
implementations of one scan is how a validator starts disagreeing with the
document it validates.** So the loop moved here, one per series, ported
verbatim: `current_max()` is what each minter used to compute inline, and
`next_seq()` is that plus the floor.

⚠ **The scans are NOT all the same shape, and flattening them would be a
  silent defect.** Three modes, and each one is somebody's deliberate decision:

  * `FY_FIELD` — filter on the record's own `fy` key, then take the digit tail.
    Seven series do this.
  * `SERIES_PREFIX` — match `/<SERIES>/<fy>/` **in the string** rather than
    trusting the `fy` key. Only `RI` does this, and `ra.py`'s own comment says
    why: *"a legacy `SF/TI/26-27/0007` typed into this field by an operator
    contributes nothing to the `RI` sequence — it is not an `RI` number and
    must not move one."* A record's `fy` key is right for that bill; the
    `tax_invoice_ref` on it may be from another series entirely.
  * `WHOLE` — no financial-year filter at all, split on `-` rather than `/`.
    Only the proforma (`PI-0007`), which is not year-scoped and whose own
    docstring records that as needing the client's numbering policy first.

## What is NOT here

⚠ **`quotation._next_ref()` is NOT in this table and gets no floor.**
  `quotation.py` is frozen (INTRODUCTION.md §7) and the thirty-first §0 block
  declines to open a fifth carve-out for this. It is also the one series where
  a floor buys nothing statutory: Rule 46(b) governs a **tax invoice**, and a
  quotation is an offer. It keeps its `len()+1` (§7.5's own older finding).

⚠ **The draft PO and the delivery challan are NOT here either**, and their
  behaviour is unchanged. They are **stored high-water counters**, not
  `max+1` scans — `challan.next_ref()`'s comment is explicit that deleting a
  challan must *spend* its number rather than hand it back — so a floor would
  be a second, weaker mechanism competing with a stronger one that already
  works and that the client's own paper book is the evidence for. They appear
  in the `/settings` section beside these, as one place to see every series,
  and they post the fields they always did.

⚠ **`ra.next_ra_no()` is NOT a document series.** It is the per-project RA
  sequence (`RA1`, `RA2`, …), reset per BOQ by design and the deliberate
  opposite of a global counter. A single floor across every project would be
  meaningless.

## Concurrency — unchanged, and deliberately so

⚠ **The minters stay unguarded scan-max-then-plus-one, and nothing here adds a
  lock.** Two threads can read the same max and mint the same number; that is
  why `gunicorn` runs `--workers 1 --threads 1` and why DEPLOY.md §8.2 calls
  `--threads 1` load-bearing rather than a tuning preference. The floor changes
  **where a series starts**, never **how a number is taken**. Do not read the
  existence of this module as the race being closed: it is not, and a floor
  makes a collision neither more nor less likely.
"""

from store import STORE

# The settings record. Its own key, NOT a branding override — see the header.
FLOORS_RECORD = "document_series_floors"

# The scope key a non-FY series files its single floor under. A sentinel rather
# than `None`, because this record is persisted as JSON and a JSON object key
# is always a string.
GLOBAL_SCOPE = "*"


# ── how a series finds its highest issued number ───────────────────────────
FY_FIELD = "fy_field"          # filter on the record's `fy` key
SERIES_PREFIX = "series_prefix"  # match /<SERIES>/<fy>/ in the string itself
WHOLE = "whole"                # no FY filter; `PI-0007` splits on `-`


class Series:
    """One numbered series: where it is stored, and how its max is read."""

    def __init__(self, key, label, collection, field, mode, fy_scoped,
                 code="", sample="", note=""):
        self.key = key                  # the stable id the floor is filed under
        self.label = label              # what /settings calls it
        self.collection = collection    # STORE[...] it scans
        self.field = field              # the record key holding the number
        self.mode = mode
        self.fy_scoped = fy_scoped
        self.code = code                # the series segment, e.g. "RI"
        self.sample = sample            # what one looks like, for the form
        self.note = note                # the sentence /settings prints

    # ⚠ Ported VERBATIM from each minter — see the header. Changing one of
    #   these changes what a statutory number is, not how it is displayed.
    def current_max(self, scope: str) -> int:
        """The highest number already issued in this scope. 0 when none."""
        highest = 0
        for rec in (STORE.get(self.collection) or {}).values():
            raw = str(rec.get(self.field) or "")
            if not raw:
                continue
            if self.mode == FY_FIELD:
                if rec.get("fy") != scope:
                    continue
                tail = raw.rpartition("/")[2]
            elif self.mode == SERIES_PREFIX:
                # ra.next_tax_invoice_ref()'s own test, unchanged: the number
                # must be in THIS series, whatever the record's `fy` key says.
                if (f"/{self.code}/{scope}/" not in raw
                        and not raw.startswith(f"{self.code}/{scope}/")):
                    continue
                tail = raw.rpartition("/")[2]
            else:  # WHOLE
                tail = raw.rpartition("-")[2]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return highest

    def scope_for(self, fy: str) -> str:
        """
        The numbering scope a date falls in.

        **The financial year for an FY-reset series, and the whole series for
        one that does not reset.** This is the line that makes a floor set for
        26-27 inert in 27-28 — see `floor_of()`.
        """
        return fy if self.fy_scoped else GLOBAL_SCOPE


# ── the registry ───────────────────────────────────────────────────────────
#
# Order is the order /settings draws them: the statutory ones first.
SERIES = (
    Series("TI", "Tax invoice", "invoices", "ref", FY_FIELD, True,
           code="TI", sample="SF/TI/26-27/0001",
           note="Rule 46(b): unique within the financial year, and capped at "
                "16 characters. Restarts at 0001 each April."),
    Series("RI", "RA bill — tax invoice number", "ra_bills", "tax_invoice_ref",
           SERIES_PREFIX, True, code="RI", sample="SF/RI/26-27/0001",
           note="The statutory serial on a single-leg RA bill, and a different "
                "series from the RA number itself. A value typed by hand in "
                "another series' shape is skipped, never parsed."),
    Series("MI", "Merged RA — tax invoice number", "merged_ras",
           "tax_invoice_ref", FY_FIELD, True, code="MI",
           sample="SF/MI/26-27/0001",
           note="The statutory serial on a merged supply + installation "
                "document. Its own series, so it can never repeat one of the "
                "other two."),
    Series("PI", "Proforma invoice", "proformas", "ref", WHOLE, False,
           code="PI", sample="PI-0001",
           note="Not financial-year scoped — one running series. A proforma is "
                "a request for money, not a tax invoice."),
    Series("RA", "RA bill — document number", "ra_bills", "ref", FY_FIELD, True,
           code="RA", sample="SF/RA/26-27/0001",
           note="Our own document number, and the key a payment is filed "
                "against. Not the statutory serial — that is the RA tax "
                "invoice number above."),
    Series("BOQ", "Bill of quantities", "boqs", "ref", FY_FIELD, True,
           code="BOQ", sample="SF/BOQ/26-27/0001",
           note="Restarts each April, like the tax invoice, and for the same "
                "reason of shape rather than statute."),
    Series("MS", "Measurement sheet", "measurements", "ref", FY_FIELD, True,
           code="MS", sample="SF/MS/26-27/0001",
           note="A sheet somebody signs on site. A gap must never re-issue a "
                "number that has already been on one."),
    Series("RCPT", "Receipt", "receipts", "ref", FY_FIELD, True,
           code="RCPT", sample="SF/RCPT/26-27/0001",
           note="Money received against an RA bill. The number is quoted on a "
                "remittance advice."),
    Series("PO", "Purchase order (we are the buyer)", "purchases", "ref",
           FY_FIELD, True, code="PO", sample="SF/PO/26-27/0001",
           note="Our own buy-side series. Rule 46 governs what we ISSUE as a "
                "supplier, so no statutory cap applies — but the vendor quotes "
                "this number back on their invoice."),
)

BY_KEY = {s.key: s for s in SERIES}


# ── the stored floors ──────────────────────────────────────────────────────

def floors() -> dict:
    """
    The whole record: `{series_key: {scope_key: int}}`.

    A copy, so a caller cannot mutate the store by accident. Returns `{}` when
    nothing has ever been set, which is the normal configuration.
    """
    saved = (STORE.get("settings") or {}).get(FLOORS_RECORD) or {}
    out = {}
    for key, scopes in saved.items():
        if key not in BY_KEY or not isinstance(scopes, dict):
            continue
        clean = {}
        for scope, value in scopes.items():
            try:
                n = int(value)
            except (TypeError, ValueError):
                continue
            if n > 0:
                clean[str(scope)] = n
        if clean:
            out[key] = clean
    return out


def floor_of(key: str, scope: str) -> int:
    """
    The floor for one series in one scope, or 0 for "none set".

    ⚠ **THIS IS WHERE AN FY-SCOPED FLOOR EXPIRES, and it expires by doing
      nothing.** A floor set for `26-27` is filed under `"26-27"`; asked for
      `27-28` this returns 0, so the April reset to `0001` under Rule 46(b)
      happens exactly as it always did. That is the whole of the answer gap 36
      said had to come from the client's numbering policy before this was worth
      writing: **a floor applies to the year it was set for and to no other**,
      which is the only reading under which a floor can never repeat a number
      across years.

      A non-FY series files its one floor under `GLOBAL_SCOPE` and it never
      expires, because that series has no reset to survive.
    """
    return int(floors().get(key, {}).get(scope, 0) or 0)


def save_floor(key: str, scope: str, value) -> None:
    """
    Write one floor, or remove it when `value` is blank or zero.

    Only non-empty values are stored, exactly as `save_po_series()` and
    `save_dc_series()` do — and the whole record is dropped when the last floor
    goes, so a store with no floors set is byte-identical to one that never had
    any.
    """
    settings = STORE.setdefault("settings", {})
    record = dict(settings.get(FLOORS_RECORD) or {})
    scopes = dict(record.get(key) or {})

    try:
        n = int(str(value).strip()) if str(value or "").strip() else 0
    except (TypeError, ValueError):
        n = 0

    if n > 0:
        scopes[str(scope)] = n
    else:
        scopes.pop(str(scope), None)

    if scopes:
        record[key] = scopes
    else:
        record.pop(key, None)

    if record:
        settings[FLOORS_RECORD] = record
    else:
        settings.pop(FLOORS_RECORD, None)


# ── the rule ───────────────────────────────────────────────────────────────

def next_seq(key: str, fy: str) -> int:
    """
    The next ordinal for a series — **the one rule, and every minter calls it**.

        next = max(existing max in the current scope + 1, floor)

    ⚠ A blank floor gives `highest + 1`, which is what every minter computed
      inline before 25 September 2026. That is why no golden moved.

    ⚠ **`max()`, not "the floor wins".** A floor at or below where the series
      has already reached does nothing — it cannot pull a series backwards and
      re-issue a number that is already on somebody's document. `/settings`
      refuses such a floor at the POST rather than accepting one that would be
      silently inert, but the arithmetic here is what makes it *safe* either
      way.
    """
    s = BY_KEY[key]
    scope = s.scope_for(fy)
    return max(s.current_max(scope) + 1, floor_of(key, scope))


def current_max(key: str, fy: str) -> int:
    """
    The highest number already issued, for the message `/settings` prints.

    The same scan `next_seq()` uses — that is the point of it living here.
    """
    s = BY_KEY[key]
    return s.current_max(s.scope_for(fy))
