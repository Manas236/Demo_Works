# STATE — where the work has got to

> **This file owns:** current phase state, what each Phase 4 step shipped, the
> open items, the known gaps, and what comes next in order.
>
> **This file does not own:** *why* any rule exists (→ [DOMAIN.md](DOMAIN.md)),
> how anything is built (→ [ABOUT.md](ABOUT.md)), or the working protocol
> (→ [INTRODUCTION.md](INTRODUCTION.md) §5).
>
> **This is the file most likely to go stale.** It links rather than restates
> for exactly that reason. Update it when a step lands.

**As of:** branch `antigravity-dev`, 15 August 2026.
**Tests:** **747 passing** in a venv with openpyxl and both client workbooks
present; **744 passed / 3 skipped** without the workbooks; **743 passed /
1 skipped** without openpyxl. All three measured by running the suite in that
configuration; a count quoted without its configuration is not a count. [ABOUT.md §1](ABOUT.md) has the table and explains
why the two mechanisms produce different-looking numbers — a module-level
`importorskip` reports **one** skip however many tests sit behind it.
**Stack:** Flask, ~12k lines, MySQL. `requirements.txt` is committed and
pinned, and `.venv` is the supported way to run this repo (§3.1 is closed).

*(The staleness banner that stood here is gone: §1 below was rewritten on
15 August 2026 and now matches the code. It had described steps 3 and 4 as not
started while both were shipped.)*

---

## 1. Phase 4 — RA billing

The approved plan and its decision record are in
[PHASE4_RA_DESIGN.md](PHASE4_RA_DESIGN.md). Four steps, each stopping and
reporting.

| Step | What it is | Status |
|---|---|---|
| — | The design, approved with amendments | ✅ `ce76e25` |
| **1** | Record shape, the revision chain, `claimed_by_line()` — with tests, before any UI | ✅ `19c3ffb` |
| **1.5** | An opaque `line_id`, and the over-claim guard re-keyed onto it | ✅ `af00d84` (design), `2ed9d05` (code) |
| **2** | The RA entry form | ✅ `fe629d5` |
| **3** | The RA register | ✅ shipped |
| **4** | The printed RA bill, with the tax block | ✅ shipped |

⚠ **Step 3 was specified as "the register **and the certification entry UI**",
and the certification half no longer exists.** Both were built; the
certification entry UI was then removed in full on 15 August 2026 at the
client's request — CLIENT_CHANGES.md item 3, under the §0 override. The register
is what remains of step 3. This is recorded rather than tidied away, because a
step that reads as simply "done" would hide that half of it was built, shipped
and then deliberately deleted.

Step 1.5 was inserted between 1 and 2 after `item_no` was found ambiguous
*within* a single BOQ, not merely across revisions. [DOMAIN.md §2.2](DOMAIN.md)
has what that cost on the client's real schedule.

### 1.1 What step 1 shipped

The record shape, `approved_by_line()` [ra.py:306](ra.py#L306),
`claimed_by_line()` walking the whole revision chain
[ra.py:385](ra.py#L385), the over-claim block, and the arithmetic — with no
routes at all. `ra.py` existed and was not reachable from a browser.

### 1.2 What step 1.5 shipped

`line_id`, minted at [boq.py:291](boq.py#L291), and both the approved and
claimed maps re-keyed onto it. Four round-trip paths for a posted id, each
tested in [tests/test_boq_line_ids.py](tests/test_boq_line_ids.py). A one-time
backfill for records written before the field
([boq.py:625](boq.py#L625), driven by `tools/backfill_line_ids.py`) — idempotent,
fills blanks only, and **counts rather than guesses** the claims it cannot
repair. `boq.revision_blockers()` [boq.py:690](boq.py#L690) refuses to delete a
claimed line.

### 1.3 What step 2 shipped

Taken from the commit body of `fe629d5`.

- Registers the `ra` blueprint — which closed a `BuildError` 500 on
  `/boq/view` that had existed since `ra_bills` records became possible.
- **Every line of the approved BOQ renders, in BOQ order, claim quantity
  defaulting to 0.** Never a shortlist. Exhausted lines grey out with the
  balance called out rather than being hidden. Zero-quantity lines are dropped
  on save — sparse storage, complete display.
- **One leg per bill by construction** ([DOMAIN.md §3.2](DOMAIN.md)).
  `ra_no` is server-assigned on save, so out-of-order and duplicate RA numbers
  are impossible rather than rejected.
- **Matching is `line_id` everywhere**; `item_no` is snapshotted onto the claim
  row and never re-derived. Documents print the snapshot; the view screen shows
  `(now 18)` beside it where a revision has renumbered.
- ~~**Two edit permissions on one record** — the claim freezes, the certificate
  never does.~~ **Retired 15 August 2026 with certification** (§1.6). What
  survives is the position gate, `claim_is_frozen()`, now one of the two gates
  in `can_edit()`.
- **Delete** is POST-only behind a confirmation page and allowed on the highest
  `ra_no` only — with the reason shown, not the button hidden. Its refusal for
  a bill carrying certification data became a refusal for an **issued** one
  (§1.6).
- `MAX_RA_LINES` is derived from `boq.MAX_LINES` [ra.py:125](ra.py#L125);
  `MAX_RA_JSON_BYTES` is **measured**, not copied
  [ra.py:156](ra.py#L156).

### 1.4 What step 2 deliberately did not ship

*All three items here were later shipped: the `/ra/` register and the printed
document both stand, and the certification entry UI was built and then removed
in full (§1.6).*

---

### 1.5 The receipts ledger — CLIENT_CHANGES.md item 8 · ✅ 14 August 2026

Money **received** against an RA bill, and the unpaid balance carried onto the
next bill of the same BOQ chain as a memo line.

⚠ **Built under the §0 override in [CLIENT_CHANGES.md](CLIENT_CHANGES.md)**,
with quotation MG/SF/2026-02 still unsigned. New scope, still chargeable there.

- `STORE["receipts"]` — its own collection, in `db.COLLECTIONS`, keyed to the
  bill it pays. Never embedded on the bill or the BOQ.
- `receipt.py` — the ledger and the add/edit/delete pages.
  **`receipt.py ──► ra.py`, never the reverse**; the balance arithmetic lives
  in `ra.py` because `create_ra()` has to snapshot at save.
  [ABOUT.md §2c](ABOUT.md).
- `prev_balance` / `prev_balance_refs` on the RA bill — **frozen at create**,
  never recomputed at print or on edit, optional and never backfilled.
- The carried balance is a **memo**: no claim row, no GST, invisible to the
  over-claim guard. ⚠ **On an assumption the client has not confirmed** —
  CLIENT_CHANGES.md §3 item 3b.
- `ra.can_delete()` refuses a bill with receipts against it.
- `tests/test_receipts.py` — 44 tests, including a byte-identical print
  assertion across a receipt being added, edited and deleted underneath an
  issued bill.

---

### 1.6 Certification removed, lifecycle installed — CLIENT_CHANGES.md item 3 · ✅ 15 August 2026

⚠ **Built under the §0 override in [CLIENT_CHANGES.md](CLIENT_CHANGES.md)**,
with MG/SF/2026-02 still unsigned. New scope, **chargeable** there — Section 7
prices it at Rs 4,000. The override block was **extended**, not overwritten.

- **Certification is gone entirely.** `/ra/certify/<id>`, `certified_qty` /
  `certified_rate` / `certified_on`, the certified columns on `/ra/print`,
  `/ra/view` and the register, and nine helpers. Nothing survives in code.
- **`status` ∈ `draft | issued | cancelled`** replaced the lock certification
  was providing as a side effect. An issued bill refuses edit and delete; a
  cancelled one is locked, excluded from every total and from outstanding, and
  cannot be un-cancelled. [ABOUT.md §3](ABOUT.md), *"The lifecycle"*.
- **`ra_no` is never reused.** Cancelled RA3 stays RA3 and the next is RA4.
- **The over-claim guard counts drafts and excludes cancelled bills.** Two
  drafts each claiming a line's whole balance are both caught; cancelling
  releases the quantity back. `OVERCLAIM_TOLERANCE` is unchanged at `0.0` and
  the control constants in `tests/test_boq_line_ids.py` did not move.
- **`GET,POST /ra/issue/<id>` and `/ra/cancel/<id>`** — `9d060ee`'s shape: GET
  confirms, POST mutates, no browser `confirm()`. §7.9f's `url_map` sweep does
  **not** cover either, so each brings its own GET-changes-nothing test.
- **A receipt may only be recorded against an ISSUED bill**; cancelling a bill
  with receipts is refused in `can_delete()`'s shape.
- `tools/strip_certification.py` — one-shot, idempotent, **not wired into
  startup**. Applied to the working database: **2 bills, 6 keys across 2 claim
  rows**, both `draft` → `issued`.
- ⚠ **It opened a real hole:** there is now no way to record that the main
  contractor allowed less than was claimed, and no credit-note flow, so
  outstanding is overstated for any bill certified down.
  **[ABOUT.md §7](ABOUT.md) gap 17** — raise it before item 2 is built.

---

### 1.7 Client segregation, the draft PO, and one shared printed sheet · ✅ 15 August 2026

⚠ **Items 2 and 4 were built under the §0 override in
[CLIENT_CHANGES.md](CLIENT_CHANGES.md)**, with MG/SF/2026-02 still unsigned.
Both are new scope and **chargeable** there. **Item 4 is not named in that
override block** and needs one of its own or the signature — recorded in
CLIENT_CHANGES.md §0 and in item 4's entry, not resolved here.

- **`client.py` — `/client/`** (CLIENT_CHANGES.md item 2). BOQs grouped by the
  billed-to party; schedule value, issued, received, outstanding. **Issued
  bills only**, less receipts, computed live. Near-duplicate names are
  **reported and never merged**. [ABOUT.md §5](ABOUT.md) (`/client`).
- **The party-edit lock was narrowed.** Draft and issued bills freeze the
  fields; **a cancelled bill alone no longer does**, because it can never be
  deleted or un-cancelled and was therefore freezing a customer name
  permanently. A GET now renders the form **read-only** instead of bouncing.
  Where a bill's frozen snapshot and the live schedule disagree, `/ra/view`
  raises the receipts band's amber divergence notice — `ra.party_drift()`.
- **`po_draft.py` — `/po/`** (CLIENT_CHANGES.md item 4). Draft PO from a BOQ:
  description and quantity only, **no rates, no GST**, a `Pcs` column, one
  **global** number series editable at `/settings` whose numbers are never
  released. A checkbox **line picker** — every box ticked, only ticked lines
  snapshotted, none ticked refused.
- **`docsheet.py` — the shared printed sheet.** Letterhead, party block, table
  shell, totals rows, bank block, signature: one copy, rendered by the
  proforma, the tax invoice, the purchase order, the RA bill and the draft PO.
  A **leaf** — it imports nothing that prints, which is what lets the RA bill
  and the tax invoice share a letterhead while `ra.py` still may not import
  `invoice.py`. [ABOUT.md §2d](ABOUT.md).
- **`/ra/print` was rebuilt on that sheet.** It had a layout entirely of its
  own — no letterhead, no page frame, Western digit grouping — on a document
  their real one heads TAX INVOICE. Every figure, item number and HSN/SAC is
  unchanged and the snapshot contract is untouched.
- [tests/test_print_golden.py](tests/test_print_golden.py) hashes the four
  printed documents and asserts the RA bill's letterhead is **byte-identical**
  to the tax invoice's.

---

## 2. What comes next

### 2.1 The tax-invoice requirement — mostly shipped

[DOMAIN.md §4](DOMAIN.md) is the requirement in full. The client's real
as-submitted RA bill is headed **TAX INVOICE**, and `ra.py` used to assert the
opposite in code and in a test over its own AST.

**That assertion has been inverted, not deleted** —
`test_ra_carries_tax_invoice_record_shape` requires the tax block and
`test_ra_forbids_improper_tax_coupling` still forbids `_tax_lines`, `invoice.py`
and the e-invoicing tokens (DOMAIN.md §4.9: per-assertion, not wholesale). The
tax block, the per-slab arithmetic, the per-line HSN/SAC snapshot, the PO/WO
reference, the Rounding Off line and the printed sheet are all shipped.

**What is NOT shipped**, and still needs an approved plan before any code
([INTRODUCTION.md §5.1](INTRODUCTION.md)):

- **The tax HEAD.** `tax_type` defaults to `cgst_sgst`, no form offers the
  choice, and nothing derives it. Pending the client's CA —
  [ABOUT.md §7](ABOUT.md) gap 15 and DOMAIN.md §4.3. **Do not encode a guess.**
- **Place of supply with its State code**, a Rule 46 field, absent from the
  document entirely. Same gap, same reason.
- **A tax invoice number as its own series**, not derived from `ra_no`
  (DOMAIN.md §4.2). `tax_invoice_ref` is captured on the record but is a typed
  field, not a generated series.

Its parts, and where each landed:

| Part | Touches | Status |
|---|---|---|
| Invert the AST assertion | `tests/test_ra_record.py` | ✅ inverted, not deleted — per-assertion, [DOMAIN.md §4.9](DOMAIN.md) |
| HSN/SAC storable per BOQ line, snapshotted onto the claim row | `boq.py`, `ra.py` — **record shape** | ✅ shipped — [DOMAIN.md §4.4](DOMAIN.md) |
| A tax invoice number as its own series | `ra.py` | ❌ **not built.** `tax_invoice_ref` is typed, not generated — [DOMAIN.md §4.2](DOMAIN.md) |
| Party GSTINs and states; the head decided by comparing them | `ra.py` | ❌ **not built, and must not be guessed at** — gap 15, [DOMAIN.md §4.3](DOMAIN.md) |
| Main contractor's PO / Work Order number and date | `ra.py` | ✅ shipped (`po_ref`, `po_date`) |
| CGST/SGST/IGST computation, and the Rounding Off line | `ra.py` — **its own, not `_tax_lines`** | ✅ shipped, per rate slab — gap 14 closed |
| The tax block on the printed sheet | Step 4 | ✅ shipped — [DOMAIN.md §4.6](DOMAIN.md) |

**Dead-Premise Cleanup Checklist — closed 15 August 2026**

The dead premise that "an RA bill is not a tax invoice":

- [x] `ABOUT.md` — Module map description
- [x] `PHASE4_RA_DESIGN.md` — Design document scope
- [x] `boq.py` — Comment describing `PRINT_TAX`
- [x] `store.py` — Comment on `ra_bills` dictionary
- [x] **[ASSERTION]** `tests/test_ra_record.py` — inverted
- [x] **[ASSERTION]** `tests/test_import_directions.py` — assertion message
- [x] `ra.py` — module docstring
- [x] `ra.py` — the `_tax_lines` import comment. ⚠ **This was ticked before it
      was true.** The comment still read *"an RA bill is a claim document, not a
      tax invoice"* until 15 August 2026, when it was corrected to state the
      three reasons the `_tax_lines` prohibition actually rests on (DOMAIN.md
      §4.9) — reasons that survive the inversion untouched.
- [x] `tests/test_ra_record.py` — the section banner still read *"An RA bill is
      NOT a tax invoice"* above assertions that said the opposite. Corrected
      15 August 2026.
- [x] `ra.py` — the receipts-block comment
- [x] `app.py` — blueprint registration comment

*Line numbers were dropped from this list on 15 August 2026: they had all
drifted, and a checklist that points at the wrong line is worse than one that
names the file.*

### 2.2 Steps 3 and 4 are shipped

Both landed. What each carries is in [ABOUT.md §5](ABOUT.md) (`/ra`); step 3's
certification entry UI was subsequently removed in full (§1.6).

---

## 3. Open items

### 3.1 Immediate

*All three items that stood here on 8 August are done, and are deleted rather
than struck through, per §5.* `requirements.txt` is committed and pinned and
`.venv` is the supported way to run the repo ([ABOUT.md §1](ABOUT.md));
`Quote.html` is in `.gitignore`; `SAMRUDHI_SPEC.md` is gone from the repo root.

Nothing is outstanding here.

### 3.2 Specified but not built

- **A revision may not lower a line's quantity below what is already claimed.**
  Specified; not built. **The BOQ revision route does not exist at all** — no
  record currently writes a non-empty `supersedes`, though every consumer
  handles the chain correctly.

### 3.3 Recorded from the client's documents, not scoped

Real, and they shape future design. **Do not build these.**

- **Delivery challan** — a document type their business uses and this system
  has no equivalent for. [DOMAIN.md §5.1](DOMAIN.md).
- ~~**Their purchase orders** differ from what `purchase.py` models — no GST, one
  running series across all suppliers and sites, a `Pcs` column on one variant.~~
  ✅ **Built as `po_draft.py` / `/po`** on 15 August 2026 (§1.7), as a
  BOQ-chain document rather than a change to `purchase.py`. All three
  differences are honoured. `purchase.py` itself is unchanged and still models
  the buy-side order it always did. [DOMAIN.md §5.2](DOMAIN.md).
- **Site is a first-class field, not a label** — they run several projects
  concurrently. [DOMAIN.md §1](DOMAIN.md).

### 3.4 Left open by the RA design, on purpose

Recorded rather than solved, in [PHASE4_RA_DESIGN.md §6](PHASE4_RA_DESIGN.md):

| | |
|---|---|
| **No value guard** (§6.2) | The over-claim guard is on quantity only. Because an RA rate may legitimately differ ([DOMAIN.md §3.6](DOMAIN.md)), a bill can be within quantity and still exceed the approved value. A real hole on a rate-contract project. |
| **No measurement sheet** (§6.4) | A claimed quantity is asserted, not substantiated. Real RA billing backs each figure with an abstract of measurements. |
| **Concurrency** (§6.6) | Two simultaneous RA creations can read the same `max(ra_no)`. Pre-existing across the whole app, not introduced by RA. Not worth a lock yet. |
| ~~**No void or cancel** (§6.7)~~ | ✅ **Closed 15 August 2026.** `/ra/cancel/<id>` withdraws a bill without destroying it, keeping `ra_no` spent and releasing the claimed quantity. §1.6. |
| **One rate per line per bill** (§6.8) | Matches their data. A part quantity claimed at a varied rate cannot be expressed. |

⚠ **And one gap that this work opened rather than closed:** removing
certification left nowhere to record that the main contractor allowed less than
was claimed, so outstanding is overstated for any bill certified down.
[ABOUT.md §7](ABOUT.md) gap 17.

### 3.5 Deferred deliberately — out of scope for you

- **`product.py`** — no escaping across ~1,409 lines.
- **`quotation.py`** — five sinks, three of which removing
  `render_template_string` does not fix.

Both are the older sell chain. Both must be fixed before any white-label
deployment. **Neither is now.** [INTRODUCTION.md §7](INTRODUCTION.md) is the
rule; [ABOUT.md §7.7 and §7.9d](ABOUT.md) hold the detail.

### 3.6 Gaps in code that already exists

Owned by **[ABOUT.md §7](ABOUT.md)** and not duplicated here — the missing
product edit route, the inconsistent escaping, the placeholder HSN codes, the
specimen company identity, the absence of a credit-note flow, e-invoicing.

Read it before proposing a fix. What you are about to report is probably
already there, with the reason it has not been done.

---

## 4. A known architectural ceiling — not a bug

One BOQ is one JSON blob, and RA billing must run against a **single approved
BOQ**, so an oversized schedule cannot be split without breaking the billing
chain. The same ceiling is why `sync()` costs roughly 216 ms per request at 50
BOQs.

**This is acceptable at this client's scale and is not to be refactored.** The
caps that keep it inside the ceiling are enforced in the view layer — never in
persistence, because `sync()` runs from `teardown_request` after the response
has gone ([ABOUT.md §4](ABOUT.md)).

---

## 5. Keeping this file honest

When a step lands:

1. Move it to ✅ in §1 with its commit hash, and add what it shipped.
2. Move whatever it deliberately did not ship into §1.4's pattern.
3. Update the test count at the top.
4. Delete the open item it closed. Do not leave it struck through.

If a fact here contradicts the code, **the code is right and this file is
stale** — report the drift ([INTRODUCTION.md §5.6](INTRODUCTION.md)).
