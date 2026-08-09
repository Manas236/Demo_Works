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

**As of:** commit `fe629d5`, branch `antigravity-dev`, 8 August 2026.
**Tests:** **411 passing**, across 14 files in `tests/`.
**Stack:** Flask, ~12k lines, MySQL. No `requirements.txt` and no venv (§3.1).

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
| **3** | The RA register, **and the certification entry UI** | ❌ not started |
| **4** | The printed RA bill | ❌ not started |

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
- **Two edit permissions on one record** — the claim freezes, the certificate
  never does ([DOMAIN.md §3.5](DOMAIN.md)). Gate at
  [ra.py:972](ra.py#L972), writer at [ra.py:926](ra.py#L926).
- **Blank is not zero.** Certified-above-claimed warns.
- **Delete** is POST-only behind a confirmation page, allowed on the highest
  `ra_no` only, and **refused outright** for any bill carrying certification
  data — with the reason shown, not the button hidden.
- `MAX_RA_LINES` is derived from `boq.MAX_LINES` [ra.py:125](ra.py#L125);
  `MAX_RA_JSON_BYTES` is **measured**, not copied
  [ra.py:156](ra.py#L156).

### 1.4 What step 2 deliberately did not ship

- **No `/ra/` register.** The four routes are `create`, `view`, `edit`,
  `delete`. There is no list view. Step 3.
- **No printed document.** `view_ra` is a working screen; it carries no A4
  sheet. Step 4.
- **No certification entry UI.** Step 2 shipped the certification *record and
  arithmetic* only. Step 3.

---

## 2. What comes next

### 2.1 The tax-invoice requirement is the next feature

[DOMAIN.md §4](DOMAIN.md) is the requirement in full. In short: the client's
real as-submitted RA bill is headed **TAX INVOICE**, and `ra.py` currently
asserts the opposite in code and in a test over its own AST.

**Nothing about it is implemented.** It needs an approved plan before any code
([INTRODUCTION.md §5.1](INTRODUCTION.md)).

Its parts, and where each lands:

| Part | Touches | Notes |
|---|---|---|
| Invert the AST assertion | [tests/test_ra_record.py:171](tests/test_ra_record.py#L171) | **Invert, never delete.** Per-assertion, not wholesale — [DOMAIN.md §4.9](DOMAIN.md) |
| HSN/SAC storable per BOQ line, snapshotted onto the claim row | `boq.py`, `ra.py` — **record shape** | [DOMAIN.md §4.4](DOMAIN.md) |
| A tax invoice number as its own series | `ra.py` | Not derived from `ra_no` — [DOMAIN.md §4.2](DOMAIN.md) |
| Party GSTINs and states; the head decided by comparing them | `ra.py` | **Not the site** — [DOMAIN.md §4.3](DOMAIN.md) |
| Main contractor's PO / Work Order number and date | `ra.py` | |
| CGST/SGST/IGST computation, and the Rounding Off line | `ra.py` — **its own, not `_tax_lines`** | [DOMAIN.md §4.9](DOMAIN.md) |
| The tax block on the printed sheet | **Step 4** | Sparse lines, parents retained — [DOMAIN.md §4.6](DOMAIN.md) |

> ⚠ **Sequencing of remaining steps is decided. Do not re-open.**
>
> The execution order is:
> **Step 3 (RA register + certification entry UI)** -> **The HSN/SAC record-shape change** -> **Step 4 (printed RA bill with the tax block)**
>
> **Reasoning:** The register lists bills rather than lines, so it barely touches HSN/SAC. The record change is a migration over stored records and must not be the first task. Placing the record change immediately before its only consumer (the printed document in Step 4) means it is built against a real use rather than speculatively.
>
> **Stop Condition:** If your step-3 plan turns out to need line-level HSN on screen, STOP and re-raise the order rather than proceeding and retrofitting.

**Dead-Premise Cleanup Checklist**

The dead premise that "an RA bill is not a tax invoice" exists in the following files and must be removed or corrected when the tax block is built:
- [x] `ABOUT.md:116` — Module map description (Fixed)
- [x] `PHASE4_RA_DESIGN.md:308` — Design document scope (Fixed)
- [x] `boq.py:115` — Comment describing `PRINT_TAX` (Fixed)
- [x] `store.py:37` — Comment on `ra_bills` dictionary (Fixed)
- [x] **[ASSERTION]** `tests/test_ra_record.py:126` — Section header/assertion asserting RA bill is not a tax invoice (Fixed)
- [x] **[ASSERTION]** `tests/test_import_directions.py:84` — Assertion message (Fixed)
- [x] `ra.py:14` — Module docstring (Fixed)
- [x] `ra.py:67` — Inline comment (Fixed)
- [x] `ra.py:487` — Inline comment (Fixed)
- [x] `app.py:28` — Blueprint registration comment (Fixed)

### 2.2 Steps 3 and 4 remain

- **Step 3 — the RA register.** A list view, plus the certification entry UI
  that step 2 deferred (§1.4).
- **Step 4 — the printed RA bill.** The document the client actually submits.
  Layout-sensitive, and it now has to carry the tax block from
  [DOMAIN.md §4](DOMAIN.md).

---

## 3. Open items

### 3.1 Immediate

1. **No `requirements.txt` anywhere in the repo, and no venv.** Generate one
   **from the actual imports** — do not `pip freeze` a system Python into it.
   The dependency list is in [ABOUT.md §7.1](ABOUT.md), which owns it.
2. **`Quote.html` is untracked** in the working tree and would ride along in a
   `git add .`. Gitignore it or delete it.
3. **`SAMRUDHI_SPEC.md` is untracked and superseded** by this document set.
   Delete it from the repo root rather than maintaining it
   ([INTRODUCTION.md §4](INTRODUCTION.md)).

### 3.2 Specified but not built

- **A revision may not lower a line's quantity below what is already claimed.**
  Specified; not built. **The BOQ revision route does not exist at all** — no
  record currently writes a non-empty `supersedes`, though every consumer
  handles the chain correctly.

### 3.3 Recorded from the client's documents, not scoped

Real, and they shape future design. **Do not build these.**

- **Delivery challan** — a document type their business uses and this system
  has no equivalent for. [DOMAIN.md §5.1](DOMAIN.md).
- **Their purchase orders** differ from what `purchase.py` models — no GST, one
  running series across all suppliers and sites, a `Pcs` column on one variant.
  [DOMAIN.md §5.2](DOMAIN.md).
- **Site is a first-class field, not a label** — they run several projects
  concurrently. [DOMAIN.md §1](DOMAIN.md).

### 3.4 Left open by the RA design, on purpose

Recorded rather than solved, in [PHASE4_RA_DESIGN.md §6](PHASE4_RA_DESIGN.md):

| | |
|---|---|
| **No value guard** (§6.2) | The over-claim guard is on quantity only. Because an RA rate may legitimately differ ([DOMAIN.md §3.6](DOMAIN.md)), a bill can be within quantity and still exceed the approved value. A real hole on a rate-contract project. |
| **No measurement sheet** (§6.4) | A claimed quantity is asserted, not substantiated. Real RA billing backs each figure with an abstract of measurements. |
| **Concurrency** (§6.6) | Two simultaneous RA creations can read the same `max(ra_no)`. Pre-existing across the whole app, not introduced by RA. Not worth a lock yet. |
| **No void or cancel** (§6.7) | A mistake is corrected only by the next bill. A revision does not help — the error is in the claim, not the contract. |
| **One rate per line per bill** (§6.8) | Matches their data. A part quantity claimed at a varied rate cannot be expressed. |

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
