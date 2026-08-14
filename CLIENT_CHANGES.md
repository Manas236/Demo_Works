# CLIENT_CHANGES — what the client asked for

> **This file owns:** the client-facing status of every change the client has
> asked for, and the open questions we are waiting on them to answer.
>
> **This file does not own:** engineering gaps we found ourselves (→
> [ABOUT.md §7](ABOUT.md)), the ordered work queue (→ [STATE.md](STATE.md)),
> the business reasoning (→ [DOMAIN.md](DOMAIN.md)), or anything architectural
> (→ [ABOUT.md](ABOUT.md)).
>
> Where an item appears here **and** in ABOUT.md §7, this file owns the
> client-facing status and links to §7 for the technical detail. It does not
> restate it. §7 is the list of defects *we* found; this is the list of things
> *they* asked for. An item can be on both, and the two entries answer
> different questions.

---

## 0. Standing rule — read this before you act on anything below

**This file is a status record. It is NOT a work queue.**

**Gated: new scope priced into Phase 2.** Nothing here that is Pending may be
started until quotation **MG/SF/2026-02** is signed by the client. That is a
commercial gate, not an engineering one, and it is not yours to reach a view on.

**Exempt: anything already sold under MG/SF/2026-01** — defect and reachability
fixes against scope already sold. Making something we have
already been paid for actually work is not new scope. Both are recorded here as
**Delivered — no charge**, and appear in MG/SF/2026-02 as already delivered.
Items 1 and 6 are both; wiring the BOQ revision chain was another.

**If you are an agent reading this file: a gated item that is not built is not a
task.** It is a record of a conversation. Do not open a file because you read
about one here, and do not treat a Pending row as a specification you have been
handed. If you think something gated should be built now, say so and stop.

The queue lives in [STATE.md](STATE.md). This file feeds it; it is not it.

---

## 1. How we approach this work

These are the standing decisions the items below are built against. They are
not restated per item.

### 1.1 The BOQ chain is deliberately separate from the sell chain

BOQ and RA bills are their own chain, parallel to quotation → proforma → tax
invoice, and they are separated **by import direction**, not by convention:

- `ra.py` may **not** import `invoice.py`. This is the load-bearing
  prohibition — the RA bill's tax block is per rate slab and carries HSN/SAC
  per claim row, while the sell chain's is document-level.
- `boq.py` may **not** import `ra.py` (nor `proforma.py`, `invoice.py`,
  `purchase.py`, `product.py`). The BOQ view page links out with `url_for` and
  reads `STORE["ra_bills"]` directly — the one-way trick.
- `quotation._tax_lines()` stays prohibited to `ra.py` for its own separate
  reasons ([INTRODUCTION.md §7](INTRODUCTION.md)).

[tests/test_import_directions.py](tests/test_import_directions.py) fails if any
of these is reversed. Full graph in [ABOUT.md §2b](ABOUT.md).

**Consequence for the items below:** every new document hung off a BOQ (draft
PO, delivery challan, proforma) is built **in the BOQ chain**, not by reaching
into the existing `/purchase`, `/proforma` or `/invoice` module. Where the
existing module already does a similar job, that is not a reason to import it.

### 1.2 Snapshot immutability — a printed document is driven by its own rows

A document that has been issued prints from **its own stored rows**. It is
never re-read from the live BOQ, and no figure on it is recomputed at render
time.

This is not a style preference. `print_ra()` was built as a loop over the live
`boq["line_items"]` and shipped green: a line deleted from the BOQ vanished
from the printed table while its amount stayed inside the printed Claim
Subtotal — an invoice whose rows did not add up to its own total.
[tests/test_ra_print_immutability.py](tests/test_ra_print_immutability.py) is
what now holds it. Detail in [ABOUT.md §5](ABOUT.md) (`/ra`).

**Every new document below inherits this rule**, and every new figure carried
across from another record — a previous balance, a certified amount, a
consignee — is **snapshotted at save**, never derived at print.

### 1.3 Anything hung off a BOQ gets its own collection

New documents get their own top-level collection in `STORE`. They are **not**
embedded as a list on the BOQ record.

The reason is `MAX_JSON_BYTES = 300,000`, the cap that actually binds on the
BOQ form: the client's real data shape reaches it at ~428 lines, below
`MAX_LINES`. Anything appended to the BOQ record eats that headroom and pushes
the failure into the schedule editor, where the user loses work that has
nothing to do with the thing that grew. See [ABOUT.md §5](ABOUT.md) (`/boq`).

### 1.4 `line_id` is the key; `item_no` is a display label

Every reference to a BOQ line — from a claim, a challan, a PO draft, anything
— matches on `line_id`. `item_no` is what a human reads and is editable,
duplicated in the client's own data, and renumbered by revisions.

A row carrying no `line_id` matches nothing and is skipped. It does **not**
fall back to `item_no`; a fallback would resurrect the exact collapse the key
exists to end, on precisely the ambiguous lines, and would do it silently.
[ABOUT.md §3](ABOUT.md) (RA Bill) carries the arithmetic this cost.

### 1.5 No tax head or place of supply gets guessed at

Nothing below adds a place-of-supply field, changes a `tax_type` default, or
encodes a derivation of which tax head applies. **That is pending the client's
CA.** ABOUT.md §7 gap 15 is the open technical record of it; §3 of this file
is the open client-facing question.

The rate-slab work that shipped deliberately stopped at the slab —
`ra._head_split()` splits a rate across whichever head the bill already
carries and decides nothing.

---

## 2. The change list — client meeting, 10 August 2026

| # | What they asked for | Status |
|---|---|---|
| 1 | Hide Base Rate and Escalation % from the printed BOQ | ✅ **Delivered — no charge** (§0 exempt) |
| 2 | Client-wise segregation — per-client totals and outstanding | 🟠 Pending |
| 3 | Remove the certified amount / certified qty section from RA bills | 🟠 Pending |
| 4 | Draft PO from a BOQ | 🟠 Pending |
| 5 | Delivery Challan from a BOQ | 🟠 Pending |
| 6 | Raise RA1 from the BOQ | ✅ **Delivered — no charge** (§0 exempt) |
| 7 | Tax Invoice directly from the BOQ | ↩ **Answered differently** |
| 8 | Record payment received against an RA bill | 🟠 Pending |
| 9 | Employee / miscellaneous charges section | ⏸ Deferred — not scoped |
| 10 | Project folder grouping BOQs → net profit / loss | ⏸ Deferred — not scoped |

---

### 1 · Hide Base Rate and Escalation % from the printed BOQ — ✅ Delivered, no charge

Both stay visible in the app; only the issued sheet drops them.

**Delivered under MG/SF/2026-01**, and carried into MG/SF/2026-02 as already
delivered — §0's exemption, at no charge.

**Approach.** `show_rate_breakup` is the single seam, and it defaults to
**False** — the issued document is what you get unless a caller opts in.
`GET /boq/print/<id>` passes False, `/boq/view/<id>` passes True, and the two
routes differ in that one argument and nothing else, so they can never quote
different money for one schedule. The flag gates four columns (base rate and
Esc. % on each of supply and installation); on the seeded schedule the
installation Esc. % is already hidden by `HIDE_EMPTY_ESCALATION`, so the
observed drop is **three columns per section**. The document header's
**Rate Basis** meta row is gated on the same flag — naming the basis on the
very sheet those figures were removed from hands back most of what was
withheld.

**Nothing was removed from storage.** All four fields are still captured,
still stored on every line, still persisted, and still what `_derived_rate`
suggests from.

→ [ABOUT.md §5](ABOUT.md), `/boq` — *"Base rate and escalation are
deliberately NOT on the issued print"*.

---

### 2 · Client-wise segregation — 🟠 Pending

A page of per-client totals and outstanding, grouped by the billed-to party.

**Approach.** The grouping key is the party on the BOQ, so the page is only as
trustworthy as those fields. Two pieces are needed before it:

1. **A minimal BOQ edit route, party fields only.** There is no BOQ edit route
   at all today — the only way to correct a customer name is to raise a full
   revision, which forks the revision chain for a typo. This route touches the
   party block and nothing else; it is not the general BOQ edit that §7.3's
   sibling gaps describe, and it must not become one.
2. **Party fields freeze once any RA bill exists against that BOQ.** An RA
   bill snapshots the party block at save, so editing the BOQ afterwards
   produces a register that disagrees with documents already issued and
   certified. `ra.bills_of()` answers whether any exist.

Outstanding depends on item 8 (receipts). Until that lands, this page can show
billed totals only, and must say so on the page rather than showing a blank
column.

→ [ABOUT.md §7](ABOUT.md) gap 3 for the shape of the missing edit/amend flows
on the sell chain; [ABOUT.md §5](ABOUT.md) (`/boq`) for revisions.

---

### 3 · Remove the certified amount / certified qty section from RA bills — 🟠 Pending

Remove it entirely, not hide it behind a flag.

**Approach.** Certification is currently a route (`/ra/certify/<id>`) and a
status on the record, not just a block on a page, so this is a removal of a
lifecycle step and not a print change. Whatever replaces it **ships with its
own guard covering issue and cancel of the replacement**: an issued document
must not be silently editable, and a cancelled one must not release its number
for reuse. That is the same shape ABOUT.md §7 gap 3 sets out for a void flow —
a `cancelled` flag plus an overprint, never a hard delete.

If the replacement adds a delete route, ABOUT.md §7.9f's standing rule applies
in full: POST-only destruction, and **its own per-route test** asserting a GET
leaves the store unchanged. The `url_map` sweep does not cover that and will
pass a route that destroys on GET.

→ [ABOUT.md §7](ABOUT.md) gaps 3 and 9f; [ABOUT.md §5](ABOUT.md) (`/ra`).

---

### 4 · Draft PO from a BOQ — 🟠 Pending

Description and quantity only. **Rates blank. No supplier buy-rates on it.**

**Approach.** Two client constraints must hold and both are hard:

- **ONE running PO number series** across all suppliers and all sites.
- **NO GST on POs.**

Neither is satisfied by the existing `/purchase` module, which computes CGST /
SGST / IGST on every PO and numbers them through a financial-year-scoped
series (`pipeline.fy_ref`). That module is also on `boq.py`'s prohibited-import
list (§1.1). So this is a **BOQ-side draft document**, not a reuse of
`purchase.py` and not a change to it — the existing buy-side PO is a different
document with a different purpose (input tax we pay), and merging them would
put the client's "no GST" rule onto a record that legitimately needs GST.

Rates being blank is the point of the document, not an unfinished state: it
goes to a supplier to be priced. Nothing on it may read a buy-rate from the
catalogue.

⚠ **Worth confirming with the client:** "one running series" versus the FY
reset every other series in this app uses. A series that never resets and one
that resets each April are both "one series across all suppliers and sites",
and they produce different numbers.

→ [ABOUT.md §5](ABOUT.md) (`/purchase`) for what the existing PO is;
[ABOUT.md §2b](ABOUT.md) for the import rule.

---

### 5 · Delivery Challan from a BOQ — 🟠 Pending

**Approach.** DC number and date, consignee, quantity and unit. **No rates
anywhere on it** — a challan that carries money is an invoice wearing a
different heading.

Its own collection (§1.3), its own number series, its rows snapshotted at save
and matched to the BOQ on `line_id` (§1.4). The consignee is snapshotted onto
the challan, not read from the BOQ at print (§1.2).

→ [ABOUT.md §3](ABOUT.md) for the record-shape conventions a new collection
follows.

---

### 6 · Raise RA1 from the BOQ — ✅ Delivered, no charge

`/boq/view` now carries **`+ RA · Supply`** and **`+ RA · Installation`** in
its action bar, beside *Revise*.

**Built ahead of the Phase 2 gate, and correctly so** — §0's exemption. RA
billing against a BOQ was sold under MG/SF/2026-01 and the billing itself
worked; there was simply no way to reach it from the schedule on screen. That
is a reachability defect in delivered scope, the same class as the BOQ revision
chain being complete but uncalled, and it is not chargeable as new work.

**It was a smaller job than it read as, and the reason is worth keeping.**
When this was scoped, the assumption was that raising a bill from a BOQ meant
building a prefill. It did not. `/ra/create?boq=<id>&leg=<leg>` had always
built the complete claim grid from the schedule — approved quantity,
claimed-to-date, balance and rate per line — and **there is no blank RA entry
form in this app**: with no `boq` parameter the route renders its BOQ picker
instead. The only thing missing was a way in from the schedule on screen; the
operator had to leave the BOQ they were looking at and find it again in `/ra`.

**Approach.** A link, and nothing else. Built with `url_for` in the same
one-way style as the existing RA chips — `boq.py` still may not import `ra.py`
(§1.1) — and `/ra/create`, `_entry_form` and `_claim_rows` were not touched.
Two buttons because a bill covers one leg by construction.

**Offered only on the tip of a revision chain.** A claim is measured against
what is approved now, so a superseded BOQ shows no control; the *Revise* button
is suppressed by the same single predicate, and it names what replaced it, so
the page says why. One caveat is recorded in ABOUT.md §7 gap 16b: the BOQ page
and the RA picker answer "is this the tip?" with two different functions that
diverge on a hand-edited fork.

→ [ABOUT.md §5](ABOUT.md) (`/boq`) — *"RA billing starts here"*;
[tests/test_boq_ra_entry.py](tests/test_boq_ra_entry.py).

---

### 7 · Tax Invoice directly from the BOQ — ↩ Answered differently

**Not being built as its own path.** The need is met by a **full-value RA
prefill**: an RA bill claiming the full approved quantity is the tax invoice,
and `/ra/print/<id>` already renders it as one. Building a second route to the
same document would create two records that can disagree about one supply.

**Proforma Invoice from the BOQ is a separate matter — it is Pending and is
being built.** Like items 4 and 5 it is a BOQ-chain document: `boq.py` may not
import `proforma.py` (§1.1), so it does not go through the existing
`/proforma` module.

⚠ Related and **not** unlocked by this: `ra.py` still asserts in code and in a
test that an RA bill is not a tax invoice, while the client's real
as-submitted bill is headed *Tax Invoice*. That assertion is to be **inverted,
not deleted**, it is not yet implemented, and it is not to be acted on off the
back of this row — [INTRODUCTION.md §8](INTRODUCTION.md) governs it.

→ [ABOUT.md §5](ABOUT.md) (`/ra`); [DOMAIN.md](DOMAIN.md) for the
tax-invoice requirement.

---

### 8 · Record payment received against an RA bill — 🟠 Pending

Amount received, balance, and that balance carried onto the next RA bill.

**Approach.** Receipts get **their own collection** (§1.3), keyed to the bill
they pay.

**The previous-balance figure must be SNAPSHOTTED into that bill's own stored
rows and never recomputed from live receipts.** This is the same defect class
as the `print_ra` bug (§1.2): a receipt entered after RA3 was issued would
silently rewrite the balance printed on a document the client has already
received. It is the identical rule to `approved_qty` / `prev_qty` /
`balance_qty`, which are stored and never recomputed at render, and to
`proforma.prior_invoiced` before them.

**Assumption, still to be confirmed with the client:** unpaid amounts are
**not** re-billed as line items on the next RA. The carried balance is a stated
figure on the bill, not a claim row. Getting this wrong inflates the cumulative
claim against the approved schedule and would trip the over-claim block for the
wrong reason. **Do not build on this assumption until they confirm it** — it is
listed in §3.

→ [ABOUT.md §3](ABOUT.md) (RA Bill) for the frozen-figures contract;
[ABOUT.md §5](ABOUT.md) (`/ra`) for the print immutability rule.

---

### 9 · Employee / miscellaneous charges section — ⏸ Deferred

**Not scoped.** Raised in the meeting, not specified. We do not know whether
this is a deduction on an RA bill, a cost line against a project, or a payroll
concept, and the three build differently.

Nothing to link — no code exists and no design has been agreed.

---

### 10 · Project folder grouping BOQs, feeding a net profit/loss view — ⏸ Deferred

**Not scoped.** Raised in the meeting, not specified.

Worth knowing before it is scoped: job costing in this app is **material
only** — no labour, no overhead, no allocation of a stock purchase across the
jobs that consume it. A "net profit/loss" view built on what exists today
would be a gross material margin with a name that overstates it, which is a
worse outcome than not having the page.

→ [ABOUT.md §7](ABOUT.md) gap B5.

---

## 3. Open questions with the client

Answers to these are blocking. None of them may be guessed at, defaulted, or
inferred from the seeded data.

1. **The GST head / place-of-supply determination.** Which head applies —
   CGST+SGST or IGST — and the place of supply with its State code, which is a
   Rule 46 field and is absent from the printed RA bill entirely. **Pending
   their CA. It must not be guessed at**, and no default may be changed in the
   meantime. Technical detail: [ABOUT.md §7](ABOUT.md) gap 15.

2. **Whether e-invoicing applies to their turnover band.** IRN plus a signed
   QR code is mandatory under Rule 48(4) above a turnover threshold, and the
   same threshold decides how many HSN digits must print. A document out of
   this app is a valid manual tax invoice below the threshold and **not** valid
   above it. We cannot answer this from anything we hold.
   → [ABOUT.md §7](ABOUT.md) gap 9b.

3. **Retention % and mobilisation-advance figures.** The `deductions` shape
   exists and is deliberately empty; both fit it. We need their actual terms,
   per project if they differ, before anything is computed rather than typed.

4. **Five complete BOQs and five as-submitted RA bills, still outstanding
   from them.** Everything above is being designed against one real schedule
   and one real bill. The item-numbering collapse that `line_id` exists to fix
   (§1.4) was found *because* a real workbook arrived; the remaining ten
   documents are the only way to find the next one before the client does.

---

*Last updated after the client meeting of 10 August 2026. When an item's status
changes, change it here and in [STATE.md](STATE.md) — this file records the
status, STATE.md orders the work.*
