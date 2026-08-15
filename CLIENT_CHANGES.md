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

> ### ⚠ OVERRIDDEN — 14 August 2026, by Manas Gawde
>
> **The gate above was overridden, not lifted and not met.** Quotation
> **MG/SF/2026-02 was still unsigned** on 14 August 2026 when Phase 2 work
> began. Manas took the decision to proceed anyway and instructed that the
> override be recorded rather than the rule deleted.
>
> **The rule above still stands and is still the default.** It is written in
> the present tense because it is still the policy; this block is the record
> that it was consciously set aside on one occasion, by the person entitled to
> set it aside. It is not evidence that the gate never existed, and it is not a
> precedent that clears the next item.
>
> **What proceeded under the override:** item 8, the receipts ledger, built on
> 14 August 2026. Anything else Pending is **still gated** and still needs
> either the signature or its own recorded override.
>
> **This does not convert Pending work into no-charge work.** §0's exemption
> covers defect and reachability fixes against scope already sold under
> MG/SF/2026-01; it does not cover item 8, which is new scope priced into
> MG/SF/2026-02 and remains chargeable there. Starting it early changed **when**
> it was built, not **what it costs** or **who agreed to it**.
>
> **The commercial risk is the client's to carry and ours to have flagged:** if
> MG/SF/2026-02 is never signed, this work was done against an unsigned
> quotation.
>
> ---
>
> ### ⚠ EXTENDED — 15 August 2026, by Manas Gawde
>
> **A second and third item proceeded under this same override, and MG/SF/2026-02 was
> still unsigned on 15 August 2026.** This block is extended rather than
> rewritten: the 14 August decision above stands exactly as recorded, and this
> is a second occasion, not a restatement of the first.
>
> **What proceeded:** **item 3** — removing the certified amount / certified
> quantity section from RA bills, and building the draft / issued / cancelled
> lifecycle that replaces the edit lock certification was providing as a side
> effect.
> And **item 2** — Client-wise segregation, giving a top-level ledger and near-duplicate
> client detection.
>
> **Items 2 and 3 remain CHARGEABLE under MG/SF/2026-02.** Section 7 of that quotation
> prices item 3 at **Rs 4,000**, and item 2 is also chargeable. They are **not** a §0 no-charge exemption: §0 exempts defect
> and reachability fixes against scope already sold under MG/SF/2026-01, and
> these are neither. Building it early changed
> **when** it was built, not **what it costs** or **who agreed to it**.
>
> **The gate is not lifted.** Every still-Pending item — 4 and 5 — continues
> to need either the signature on MG/SF/2026-02 or its own recorded override,
> decided by the client-facing owner. Overrides are not a precedent and do
> not make a subsequent one automatic; an override remains a decision that is taken and
> recorded, never one an agent may take, infer, or extend.
>
> **The commercial risk is unchanged and is restated deliberately:** if
> MG/SF/2026-02 is never signed, items 8, 3, and 2 were built against an
> unsigned quotation.

**Exempt: anything already sold under MG/SF/2026-01** — defect and reachability
fixes against scope already sold. Making something we have
already been paid for actually work is not new scope. Both are recorded here as
**Delivered — no charge**, and appear in MG/SF/2026-02 as already delivered.
Items 1 and 6 are both; wiring the BOQ revision chain was another.

**If you are an agent reading this file: a gated item that is not built is not a
task.** It is a record of a conversation. Do not open a file because you read
about one here, and do not treat a Pending row as a specification you have been
handed. If you think something gated should be built now, say so and stop.

That rule is unchanged by the overrides above. **An override is a decision the
client-facing owner takes and records; it is not one you may take, infer, or
extend.** Items 8, 3, and 2 being built early is not licence to start item 5 —
and recorded overrides are not a precedent that makes a next one automatic.

> ⚠ **Item 4 is built and the override block does not name it.** The draft PO
> was delivered on 15 August 2026 alongside items 3 and 2, but the EXTENDED
> block above names only those two. The block is left exactly as it stands —
> amending an override to cover work it does not mention is precisely the act
> the rule above forbids. **Item 4 therefore stands built with no recorded
> override of its own, and needs one or the signature.** Recorded here rather
> than resolved, because resolving it is the client-facing owner's decision.
> Item 4's own entry carries the same note.

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
| 2 | Client-wise segregation — per-client totals and outstanding | ✅ **Delivered** — built 15 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** |
| 3 | Remove the certified amount / certified qty section from RA bills | ✅ **Delivered** — built 15 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** (Section 7, Rs 4,000) |
| 4 | Draft PO from a BOQ | ✅ **Delivered** — built 15 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** |
| 5 | Delivery Challan from a BOQ | 🟠 Pending |
| 6 | Raise RA1 from the BOQ | ✅ **Delivered — no charge** (§0 exempt) |
| 7 | Tax Invoice directly from the BOQ | ↩ **Answered differently** |
| 8 | Record payment received against an RA bill | ✅ **Delivered** — built 14 Aug 2026 under the §0 override; **chargeable under MG/SF/2026-02** |
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

### 2 · Client-wise segregation — ✅ Delivered

`/client/` — every BOQ grouped by the party it is billed to, with schedule
value, issued, received and outstanding across all of it.

⚠ **Built on 15 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** New scope, **chargeable** under that quotation. See §0's override
block, which was extended rather than overwritten.

**It is a current-state screen, not a document**, so every figure is computed
live. Outstanding is **issued bills less receipts** — a draft has not been sent
and a cancelled one has been withdrawn, and putting either into a figure
somebody is about to chase a customer for would be a demand for money that was
never made or was explicitly retracted. It is not clamped at zero: an
overpayment shows as a credit.

**Near-duplicate names are reported and never merged.** The grouping key is
`pipeline.norm_name(account_name)` — casefolded, whitespace-collapsed,
**punctuation kept** — so `Pvt Ltd` and `Pvt. Ltd.` stay two groups with an
amber band naming them. There is no `customer_id` anywhere in this app; merging
them would be the system deciding two typed names are one party, which it
cannot know (DOMAIN.md §6).

**The minimal party-edit route** (`/client/edit-party/<id>`) writes the
customer block and nothing else — no line, no rate, no quantity, no section, no
project field. It is not the general BOQ edit and must not become one; a test
posts a full set of decoys to hold that.

⚠ **Two corrections to what was first delivered**, both made on 15 August 2026:

- **A GET on a locked schedule now renders the form READ-ONLY** rather than
  bouncing. It refused on GET as well as POST, so a locked BOQ's customer
  details could not even be *looked at* from that page. The controls are
  disabled, the blocking bills are named and linked, and the POST is what
  refuses.
- **The lock was narrowed to DRAFT and ISSUED bills.** It had counted bills of
  any status, and a cancelled bill can never be deleted or un-cancelled — so
  one of them froze that BOQ's customer name permanently with no escape, and
  that client then stayed split across two rows of this very page forever. A
  cancelled bill is excluded from every other total in this app by design.
  Where a bill's frozen party snapshot and the live schedule now disagree,
  `/ra/view` raises an amber band giving both and stating that the document is
  deliberately not restated — the same divergence surface the receipts work
  established, reused rather than rewritten.

⚠ **It inherits [ABOUT.md §7](ABOUT.md) gap 17.** `outstanding_of()` is
`grand_total − receipts` and `grand_total` is what we *claimed*; there is
nowhere to record that the main contractor allowed less. This page rolls that
figure up per client, which widens where the overstatement is visible without
changing its size. §3 below carries the question for them.

→ [ABOUT.md §5](ABOUT.md) (`/client`) for the pages;
[tests/test_client_segregation.py](tests/test_client_segregation.py),
[tests/test_norm_name.py](tests/test_norm_name.py).

---

### 3 · Remove the certified amount / certified qty section from RA bills — ✅ Delivered

Removed entirely, not hidden behind a flag.

⚠ **Built on 15 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** This is **new scope and remains chargeable** under that quotation —
**Section 7 prices it at Rs 4,000** as *"RA issue + cancellation with the
certified section removed"*. It is **not** a §0 no-charge exemption: §0 exempts
defect and reachability fixes against scope already sold under MG/SF/2026-01,
and certification was neither broken nor unreachable. See §0's override block,
which was extended rather than overwritten.

**What went.** The route `/ra/certify/<id>` and its page; `certified_qty` and
`certified_rate` on every claim row; `certified_on` and the old
`draft | submitted | certified` status on the bill; the certified quantity and
amount columns on `/ra/print`, `/ra/view` and the register, with the register's
*Total Certified Amount* tile and *Certification* badge column; and every helper
that computed or validated certification — nine functions in all. Nothing about
it survives in code.

**What replaced the LOCK, which is the part the ask did not mention.**
Certification was doing two unrelated jobs: it was the main contractor's ruling,
*and* it was the only thing stopping an already-submitted bill being edited or
deleted (`has_certification()` gated `can_delete()`, and the old `status` was
the flag). Removing the ruling removed the lock, so the lock is rebuilt as an
explicit lifecycle:

| State | What it permits |
|---|---|
| `draft` | editable, deletable subject to the existing receipts guard, prints with a **DRAFT** marker |
| `issued` | `edit_ra` and `delete_ra` both refuse; prints clean; money may be receipted against it |
| `cancelled` | locked, reason and date recorded, excluded from every total and from outstanding, **cannot be un-cancelled**, prints over a CANCELLED overprint |

**`ra_no` is never reused.** A cancelled RA3 stays RA3 and the next bill is RA4,
the same reasoning that stops a GST serial being reissued — the number has been
quoted in somebody else's ledger. `next_ra_no()` counts cancelled bills, which
makes that true by construction rather than by a rule somebody remembers.

**The over-claim guard now counts drafts and excludes cancelled bills.** Both
halves are load-bearing and neither is obvious: two drafts each claiming a
line's whole remaining balance are both caught, and cancelling a bill releases
its quantity back onto every line it claimed. `OVERCLAIM_TOLERANCE` is still
`0.0` and the control constants are untouched.

**Receipts.** A receipt may only be recorded against an **issued** bill
(`ra.can_receipt()`, stated once and read by both `receipt.py` and the control
on `/ra/view`), and cancelling a bill that carries receipts is **refused** in
the same shape as the existing `can_delete()` refusal.

**Routes** are `GET,POST /ra/issue/<id>` and `GET,POST /ra/cancel/<id>`,
following `9d060ee`'s shape exactly: the GET renders a confirmation page and
mutates nothing, the state change happens only in the POST branch, and there is
no browser `confirm()` anywhere. ABOUT.md §7.9f's `url_map` sweep only walks
rules whose path contains "delete", so **neither route is covered by it** and
each ships its own test asserting a GET changes no status.

**Data migration.** `tools/strip_certification.py` — one-shot, idempotent, not
wired into startup. Applied to the working database on 15 August 2026:
**2 bills, 6 certification keys across 2 claim rows**, both migrated from
`draft` to `issued`. Every existing bill becomes `issued` and none is left a
draft: the old `status` was a certification-tracking field with no gate attached
to it, so a stored `"draft"` said nothing about whether the bill was sent.

⚠ **What this cost, stated plainly:** any certified quantity or rate already
keyed in is destroyed and is recoverable only from the dated dump in
`backups/`. That is what "remove it entirely" means.

⚠ **And what it leaves open:** there is now **no way to record that the main
contractor allowed less than was claimed**, and no credit-note flow to correct
it, so outstanding is overstated for any bill certified down. New in
[ABOUT.md §7](ABOUT.md) gap 17.

→ [ABOUT.md §7](ABOUT.md) gaps 3, 9f and 17; [ABOUT.md §5](ABOUT.md) (`/ra`);
[tests/test_ra_routes.py](tests/test_ra_routes.py),
[tests/test_strip_certification.py](tests/test_strip_certification.py).

---

### 4 · Draft PO from a BOQ — ✅ Delivered

`/po/` — description and quantity only. **Rates blank. No supplier buy-rates on
it. No GST.**

⚠ **Built on 15 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** New scope, **chargeable** under that quotation.

> ⚠ **A gap in the record, reported rather than papered over.** §0's override
> block, extended on 15 August 2026, names **items 3 and 2** as what proceeded.
> **It does not name item 4**, and this item was built on the same day under the
> same circumstances. That block is left exactly as it stands — an override is a
> decision the client-facing owner takes and records, and amending one to cover
> work it does not mention is not an agent's to make. **Item 4 therefore has no
> recorded override of its own.** It needs one, or the signature.

**Built in the BOQ chain**, not by reusing `/purchase`. Two client constraints
made that necessary and both are hard: **one running PO number series** across
all suppliers and all sites, and **no GST**. The buy-side PO computes CGST /
SGST / IGST on every order and numbers through an FY-scoped series, and merging
them would put the no-GST rule onto a record that legitimately needs GST —
that PO records **input tax we pay**.

**Separate behaviour, shared appearance.** The document prints on the same A4
sheet as the buy-side PO — same letterhead, same party block, same table shell,
same signature — through the shared `docsheet.py`. It differs only where the
client asked: no GST block at all (not a zero-rated one), rates blank, and a
`Pcs` column beside `Qty`.

**Rates being blank is the point of the document, not an unfinished state.** It
goes to a supplier to be priced, and nothing on it reads a buy rate from
anywhere. The BOQ's own `supply_rate` is the dangerous one — that is what we
*sell* the work for, and printing it on the sheet handed to the person quoting
us is the worst thing this document could do. There is a test for it.

**The line picker.** `/po/create?boq=<id>` lists every BOQ line as a checkbox
row with an editable quantity defaulting to the schedule's, plus select-all and
clear-all. **Every box arrives ticked**, because most orders are the whole
schedule — but the operator can untick down to a few. Only ticked lines are
snapshotted; nothing ticked is **refused with a message**, never written as an
empty PO. A ticked size brings its specification clause with it, carrying no
quantity. Matching is on `line_id` (§1.4).

**Numbering.** The prefix and the next number are **editable at `/settings`**,
defaulting to `SF/DPO` and 1. They have to be: the client's series already
exists on paper, and a hardcoded start would collide with their book on the
first order. The counter is **global, deliberately not per-BOQ** — the opposite
of `ra_no`, which is per project because it is that job's own sequence. **A
deleted draft PO does not release its number.**

**The vendor** is a picker over the shared address book (`type: "vendor"`),
with a **free-text fallback** for a one-off supplier not worth an entry.
The brief specified free-text party fields; the address book is an improvement
on that — it carries the address and the GSTIN and cannot be spelled two ways —
so both are offered and whichever was used is snapshotted onto the PO at create.
It is **still not a vendor master**: [ABOUT.md §7](ABOUT.md) gap B6.

⚠ **Still worth confirming with the client:** "one running series" versus the FY
reset every other series in this app uses. A series that never resets and one
that resets each April are both "one series across all suppliers and sites",
and they produce different numbers. **What was built does not reset**, taking
the ask literally.

⚠ **Nothing captures the rates the supplier quotes back.** The priced copy comes
in on paper and is re-keyed into a buy-side PO, with no link between the two
documents. [ABOUT.md §7](ABOUT.md) gap B7.

→ [ABOUT.md §5](ABOUT.md) (`/po`) for the pages and (`/purchase`) for what the
existing PO is; [tests/test_po_draft.py](tests/test_po_draft.py).

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

✅ **The dead premise is closed.** `ra.py` and its tests used to assert that an
RA bill is not a tax invoice, while the client's real as-submitted bill is
headed *Tax Invoice*. The assertion was **inverted, not deleted**
(`test_ra_carries_tax_invoice_record_shape` and
`test_ra_forbids_improper_tax_coupling`), and the last two comments still
carrying the old premise — `ra.py:66-68` and the section banner in
`tests/test_ra_record.py` — were corrected on 15 August 2026 alongside item 3.

⚠ **Still not unlocked by any of that:** `quotation._tax_lines()` remains
prohibited to `ra.py` on its own three reasons, which survive the inversion
untouched — [DOMAIN.md §4.9](DOMAIN.md),
[INTRODUCTION.md §7](INTRODUCTION.md).

→ [ABOUT.md §5](ABOUT.md) (`/ra`); [DOMAIN.md](DOMAIN.md) for the
tax-invoice requirement.

---

### 8 · Record payment received against an RA bill — ✅ Delivered

Amount received, balance, and that balance carried onto the next RA bill.

⚠ **Built on 14 August 2026 under the §0 override, with MG/SF/2026-02 still
unsigned.** This is **new scope and remains chargeable** under that quotation —
it is not a §0 exemption, and starting it early changed when it was built, not
what it costs. See §0's override block.

**Built as specified.** Receipts have **their own collection**, `receipts`,
keyed to the bill they pay (§1.3) — not embedded on the RA bill and not on the
BOQ, where they would eat the headroom under `boq.MAX_JSON_BYTES`.

**The previous-balance figure is SNAPSHOTTED** onto each bill by
`ra.create_ra()` at the moment it is raised, and every renderer reads it off
that record. It is not recomputed at print, and not recomputed on edit either.
`tests/test_receipts.py` proves it the strong way: it renders a bill, then adds
a receipt, corrects another and deletes a third underneath it, and asserts the
printed page is **byte-identical**.

**Where the frozen figure and the live ledger disagree, both are shown.**
Editing or deleting a receipt after a later bill has snapshotted its effect is
**allowed** and never touches that bill; the edit form and the delete
confirmation name the bills that will not move, and `/ra/view` flags the
divergence on each of them afterwards. Refusing the correction would protect a
document that is already immune while leaving the ledger permanently wrong.
DOMAIN.md §6: surface it, name it, never silently correct it.

**Receipts follow the revision CHAIN, not the BOQ record** — a payment against
a bill raised on revision 0 still counts once revision 1 is live. Summing
against one record would reset the carried balance to zero on every revision,
which is the trap `claimed_by_line()` already exists to avoid.

⚠ **ASSUMPTION, STILL NOT CONFIRMED BY THE CLIENT — and now built on.** Unpaid
amounts are **not** re-billed as line items on the next RA; the carried balance
is a memo on the face of the bill, absent from `claim_subtotal`, from every tax
figure, from `net_payable`, from `grand_total` and from the over-claim guard.

This was previously marked *"do not build on this assumption until they confirm
it"*. It was built on anyway, on the same 14 August decision as the override
above, and the assumption is recorded in three places rather than buried: in
the record shape comment at `ra.create_ra()`, in
[ABOUT.md §3](ABOUT.md) (RA Bill), and in §3 below, which stays open.

**What changes if they say no.** An arrear re-billed as a claim row would be
taxed a second time on a value already taxed once, and would inflate the
cumulative claim against the approved schedule until the over-claim block
refused a bill for the wrong reason. The test that pins the current behaviour
(`test_the_carried_balance_is_not_billed_taxed_or_claimed`) names itself as
pinning an assumption, so it is the first thing a future reader will find.

**Also shipped, not in the original ask:** `ra.can_delete()` refuses to delete
a bill that has receipts against it — deleting one would leave the money filed
against a document that no longer exists. `/receipt/delete` is POST-only behind
a GET confirmation, with its own test that a GET destroys nothing (§7.9f).

→ [ABOUT.md §2c](ABOUT.md) for the import direction and why the arithmetic
lives in `ra.py`; [ABOUT.md §3](ABOUT.md) (Receipt) for the record shape;
[ABOUT.md §5](ABOUT.md) (`/receipt`) for the pages;
[tests/test_receipts.py](tests/test_receipts.py).

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

3b. ⚠ **Whether an unpaid amount is re-billed on the next RA, or merely
   stated.** Item 8 assumes **merely stated** — a memo line carrying no GST and
   no claim row. **This question is no longer merely open: it has been built
   on**, on the 14 August decision recorded in §0. Answering it "re-bill them"
   is a real change, not a display tweak — see item 8 for what it moves. Ask
   them before the next RA bill goes out.

4. **Five complete BOQs and five as-submitted RA bills, still outstanding
   from them.** Everything above is being designed against one real schedule
   and one real bill. The item-numbering collapse that `line_id` exists to fix
   (§1.4) was found *because* a real workbook arrived; the remaining ten
   documents are the only way to find the next one before the client does.

---

*Last updated after the client meeting of 10 August 2026. When an item's status
changes, change it here and in [STATE.md](STATE.md) — this file records the
status, STATE.md orders the work.*
