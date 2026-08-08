# Phase 4 — RA Billing · design

> **Approved with amendments, 2026-08-05.** Read [ABOUT.md](ABOUT.md) §2b, §3
> (Bill of Quantities) and §4 first; this document assumes them.
>
> The five amendments are folded in below and marked **[AMENDED]** where they
> changed what the proposal originally said. §7's open questions are now
> answered and kept only as a record of what was decided.

## Build order

1. **Record shape + `claimed_by_line()` walking the revision chain**, with
   tests, before any UI.
2. The RA entry form.
3. The register.
4. The printed RA bill.

Each step stops and reports.

---

## 0. What the client's annexure actually contains

Read from `annexure.xlsx` (Sheet2, 189 rows × 42 columns) rather than from the
description, because three things in it change the design.

| RA | column | leg | lines claimed | qty | amount |
|---|---|---|---|---|---|
| RA1 | N | supply | 19 | 1,882.71 | 34,29,065.17 |
| RA2 | Q | supply | 12 | 1,102.80 | 25,65,506.40 |
| RA3 | T | supply | 26 | 267.00 | 11,37,770.00 |
| RA5 | W | supply | 15 | 125.00 | 25,87,352.00 |
| RA7 | Z | supply | 3 | 535.00 | 4,76,032.00 |
| RA9 | AC | supply | 1 | 2.00 | 2,73,000.00 |
| RA4 | AG | installation | 10 | 523.40 | 9,96,260.00 |
| RA6 | AJ | installation | 8 | 823.55 | 3,75,650.00 |
| RA8 | AM | installation | 3 | 809.30 | 8,30,960.00 |

Each block is three columns — quantity (headed "Unit"), rate, amount. Two
balance columns close the sheet: **AF "Supply Balance"** and **AP "Installation
Balance"**. 69 of the 97 lines carry at least one claim; **11 lines are claimed
on both legs**.

**Three findings that the design has to answer to:**

1. **The three over-claims are not one kind of thing.**

   | item | BOQ qty | claimed | balance | as % |
   |---|---|---|---|---|
   | 4.2 | 12 | 12.06 | −0.06 | 0.5% |
   | 24.c | 12 | 12.06 | −0.06 | 0.5% |
   | 24.d | 35 | 46.54 | −11.54 | **33%** |

   All three are on RA1, all supply. Two are 0.5% — site measurement rounding
   on a pipe run. One is 33% — a real over-claim. **A hard block at exactly the
   approved quantity rejects all three**, including the two that are almost
   certainly correct.

   **[AMENDED] Decided: build the hard block, with the tolerance as a single
   named constant defaulting to zero.** See §6.1.

2. **The `#VALUE!` cells are not in a claim.** `AF28` and `AP28` sit on a
   *repeated header band* — `A28` reads "Sr. No." and `B28` "Description of
   Item". The balance formula was dragged down over a mid-table print header
   and subtracted text from text. It is a spreadsheet artefact, not a bad
   number in a bill. An importer must skip repeated header rows; one that does
   not will import a claim of `"#VALUE!"`.

   **[AMENDED] Out of scope for Phase 4.** Recorded in the Phase 3 import notes
   (ABOUT.md §5, the importer's section) and not handled here.

3. **The RA rate differs from the BOQ rate on 10 cells.** The claim rate is
   *not* always the approved rate. The RA line must therefore store its own
   rate as entered — the same call ABOUT.md §3 makes for `supply_rate` on a BOQ
   line, and for the same reason.

   **[AMENDED] And it must be flagged at entry when it diverges** from the
   approved BOQ rate for that line. A **warning, never a block** — rates
   legitimately move on approved variations. A rate that silently disagrees
   with the approved BOQ is one of the two failure modes this system was sold
   to catch, so it must be visible at the moment of entry rather than
   discoverable afterwards. `rate_varies` is stored on the claim row so the
   divergence is a fact about the issued bill and not a re-derivation.

---

## 1. Record shape — own record, or embedded in the BOQ?

### Recommendation: **its own record**, in a new `STORE["ra_bills"]` collection.

`boq.py` already assumes this. [boq.py:1493-1510](boq.py#L1493-L1510) reads
`STORE.get("ra_bills")`, filters on `r["boq_id"] == id`, sorts by
`int(r["ra_no"])` and links with `url_for("ra.view_ra", id=rid)`. The seam is
committed and tested; this proposal keeps it.

### What each choice costs

`sync()` re-serialises **every record in every collection on every request** to
compute its digest, so the *hashing* cost is O(total store bytes) either way and
shape does not change it. What shape changes is the **write**, and the ceiling.

Measured: the seeded 97-line BOQ record is **74,560 bytes** of JSON. An RA bill
covering 69 lines is roughly 14 KB. Nine of them is ~126 KB.

| | embedded in the BOQ | own record |
|---|---|---|
| BOQ record after 9 RA bills | 74.5 KB → **~200 KB** | unchanged at 74.5 KB |
| writing one new RA bill | rewrites the whole ~200 KB BOQ | writes ~14 KB |
| editing the BOQ | rewrites the RA bills too | untouched |
| digest churn | any RA change dirties the BOQ | independent |

Three reasons beyond the arithmetic, and the first is decisive:

- **Embedding breaks the BOQ's own form.** `MAX_JSON_BYTES` caps the BOQ
  payload at 300 KB (§5 of ABOUT.md). A BOQ record that grows to ~200 KB with
  RA bills inside it, on a schedule already allowed to be 300 KB on its own,
  **can no longer be posted back through its own editor**. The BOQ would become
  uneditable by the act of billing it.
- **An issued RA bill must not live inside a mutable document.** The whole
  sell-side chain freezes a copy at issue (§3). An RA bill embedded in the BOQ
  is a claim whose container someone can still edit.
- **A separate collection is one line in `db.COLLECTIONS`** and the table is
  created automatically on next start.

**Cost accepted, stated plainly:** `sync()`'s per-request work grows by the size
of the RA collection — ~126 KB more JSON to serialise and hash per request at
their volume. That is the known trade-off of snapshot-and-diff and is not
introduced here; the sha256 change makes the *retained* cost negligible but not
the serialisation cost. It becomes worth revisiting at roughly 20× this volume.

---

## 2. Numbering — one series, two legs

### Recommendation: `ra_no` is a **single integer sequence per BOQ**, assigned by the server, never typed. The supply/installation split is an **attribute of the bill**, not a second series.

The client's own sheet proves this is right: RA1–RA9 is one unbroken run, and
the legs alternate irregularly (supply 1,2,3,5,7,9; installation 4,6,8). There
is no "supply RA3" and "installation RA3" — there is RA3, which happens to be a
supply bill.

```python
ra_no = max((r["ra_no"] for r in ra_bills_of(boq_id)), default=0) + 1
```

**max+1, not len+1** — `proforma._next_ref()`'s precedent (§5). A gap must never
re-issue a number the client has already seen on a claim.

This makes both failure modes you named **structurally impossible rather than
validated against**:

- *RA5 before RA4* — the user never chooses the number, so there is no input to
  reject. They choose the leg; the sequence is ours.
- *Two RA6s* — the number is read and assigned inside the same guard that writes
  the record, so there is one path and it cannot produce a duplicate. (The
  residual race is in §6.6.)

### Two identifiers, doing different jobs

| field | example | scope | job |
|---|---|---|---|
| `ra_no` | `5` | per BOQ | the client's own sequence — "RA5", what appears on the certificate |
| `ref` | `SF/RA/26-27/0004` | per financial year | our document number, the key the payment is filed against |

`ref` follows `pipeline.fy_of` / `fy_ref`, shared with the tax invoice, the PO
and the BOQ. **If the RA bill is the tax invoice** (see §5, this is unresolved
and it matters), `ref` inherits Rule 46(b): unique within the FY and **≤ 16
characters**, which `SF/RA/26-27/0004` satisfies at exactly 16.

---

## 3. Cumulative claimed quantity — derived or stored?

### Recommendation: **derived**, through a single function that is the only way anything asks the question.

```python
def claimed_by_line(boq_id) -> dict:      # {(item_no, leg): qty}
```

### What derived costs at their volume

9 RA bills × 69 claimed lines = **~620 claim rows** to sum. That is a dict
accumulation over 620 items — microseconds, and it happens on the RA form, the
RA document and the BOQ view page. Ten times their volume (90 bills, 600 lines)
is ~54,000 rows and still single-digit milliseconds. The honest ceiling before
caching earns its place is around 50,000 rows, which is **80× where they are
today**.

### Why derived is not merely "correct but slower" here

A stored cumulative is a denormalisation that has to be maintained on every
create, edit, revision and delete. Any path that misses one leaves the number
silently wrong — and the number **is** the over-claim guard, the single control
this module exists to provide. A guard computed from a stale counter is worse
than no guard, because it is trusted.

Derived also survives the revision chain (§4) for free: the sum walks whatever
bills exist, so a new revision cannot orphan a counter.

**Condition on this recommendation:** it holds because RA bills are proposed as
**immutable once issued** (§6.7). If they become editable, derived is still
correct and still cheap — it is stored that would break.

---

## 4. When the approved BOQ has to change

This is the escape route the hard block makes mandatory, and it is the part of
the proposal I would most want you to push back on.

### Recommendation: a **BOQ revision** — a new record — not an edit.

`rev_no` already exists on the BOQ record and is always `0` today. It was put
there for this.

```
BOQ rev 0  ──►  RA1 … RA4          (rev 0 is what those four were measured against)
   │
   └── superseded by
BOQ rev 1  ──►  RA5 … RA9          (later bills measure against rev 1)
```

- A revision **creates a new BOQ record** carrying `rev_no + 1`, a new `id`, and
  `supersedes: <previous boq_id>`. The previous record is never mutated.
- An RA bill references a **specific revision** by `boq_id`, so an issued
  claim's basis can never move under it. The balance printed on RA3 stays true
  forever.
- `claimed_by_line()` **walks the whole revision chain** and sums across it.
  Without this a revision resets every line's claim to zero and defeats the
  guard entirely — this is the single subtlest requirement in the design.
- The **approved quantity** for the guard is the quantity on the **latest**
  revision.

### Three rules a revision must obey, and why

1. ~~**It may not renumber `item_no`.**~~ **[AMENDED — step 1.5] Withdrawn. A
   revision may renumber freely.** This rule existed because the claim history
   was matched on `item_no`, and that turned out to be unworkable for a reason
   that had nothing to do with revisions: **`item_no` is not unique inside a
   single BOQ.** It restarts per section, and the client's own section A
   carries item `17` twice. Matching on it collapsed 87 priced lines into 77
   and broke the guard in both directions at once — ₹1,99,122.50 of over-claim
   permitted, ₹84,071.00 of legitimate claim refused.

   Lines now carry an opaque server-minted **`line_id`** (ABOUT.md §3), which a
   revision carries forward unchanged for every surviving line. The claim
   history follows the id, so renumbering detaches nothing. A revision may
   change quantity, rate, description, unit **and item number**, and may add
   lines.
2. **It may not remove a line with claims against it.** There is nowhere for
   that history to go. **[step 1.5] Implemented** as
   `boq.revision_blockers()`, which names the line and the RA numbers that
   claimed it. Removing an unclaimed line is free.
3. **It may not lower a line's quantity below what is already claimed.** That
   would manufacture a retroactive over-claim on bills already issued and
   certified. Blocked at revision time, naming the line and the shortfall.
   **Still to build** — it belongs with the revision route.

### Why not a per-claim override

An override flag would be the smaller change, and I am rejecting it. You chose a
hard block, and an override recorded on a claim leaves **no document trail of
why the contract quantity changed** — the next person sees a line billed at 133%
of approved with a tick box beside it. A revision produces a document, which is
what a variation order is in the trade. The block stays hard; the revision is
the sanctioned way through it.

---

## 5. What `boq.py` gives us, and what needs writing twice

`ra.py` **may import `boq.py`** — the forbidden direction is `boq → ra`, and
[tests/test_import_directions.py](tests/test_import_directions.py) already
asserts it. So the reuse is real, not aspirational.

### Reusable as-is

| From | What | Note |
|---|---|---|
| `quotation.py` | `_inr`, `_fmt_qty`, `_amount_in_words`, `_meta`, `VIEW_DOC_STYLES`, `QUOTATION_STYLES` | the A4 sheet, imported exactly as boq.py imports it |
| `boq.py` | `BOQ_STYLES` | already landscape, which an RA sheet also needs |
| `boq.py` | `_item_no()` | **essential** — the annexure carries the same `4.0999999999999996` floats |
| `boq.py` | `_num`, `_opt_num`, `_valid_tax_code`, `section_totals` | |
| `pipeline.py` | `esc`, `parse_money`, `fy_of`, `fy_ref` | |
| `dashboard.py` | `BASE_STYLES`, `_nav()`, the `_page()` pattern | the persistence strip comes free |
| `db.py` | one entry in `COLLECTIONS` | table auto-creates |
| `boq.py` | the `MAX_JSON_BYTES` reasoning | applies to the RA form too if it posts a JSON model |

### Needs a second implementation

- **The line editor.** `_BOQ_JS` is built around sections, areas, the spec
  picker and escalation. An RA form is a different animal: **the line set is
  fixed** — it comes from the BOQ and the user must not be able to add to it.
  What they enter is one quantity per line. Reusing `_BOQ_JS` would drag the
  whole spec picker into a form that must refuse to pick anything. Write a
  smaller model; reuse the *contract* (`_open` state posted, stripped
  server-side, offending line forced open) rather than the code.
- **Validation.** `_clean_lines()` validates a schedule being authored. RA
  validation asks different questions: does this line exist in the BOQ, is the
  quantity ≥ 0, and does cumulative exceed approved. Same reject-and-re-render
  contract, different rules.
- **The printed columns.** One table per section carries over structurally, but
  the columns differ: no escalation, no area breakdown (a claim is one
  quantity), plus **previous / this claim / cumulative / balance** — the four
  columns that make it a running account rather than an invoice.
- **Numbering.** `boq._next_ref()` gives the FY series; the per-BOQ `ra_no` is
  additional.
- **Tax — [AMENDED] explicitly OUT of scope.** **An RA bill is a claim
  document, not a tax invoice.** Decided and commercially scoped: the project
  tax-invoice chain is a separate paid module later.

  > **[AMENDED 8 Aug 2026]** The first sentence is superseded: the
  > client's as-submitted RA bill is headed "Tax Invoice", so the RA
  > bill itself must carry a tax block — see DOMAIN.md §4. The
  > commercial scoping is NOT superseded. A separate project
  > proforma/tax-invoice chain remains a later chargeable module, and
  > IRN, e-invoice JSON and GSTR-1 filing remain out of scope.

  Concretely, `ra.py` must **not** have:

  | | |
  |---|---|
  | ❌ `quotation._tax_lines()` | do not import it |
  | ❌ Rule 46 fields | no HSN/SAC on the claim row, no `place_of_supply`, no `pos_code` |
  | ❌ reverse-charge declaration | |
  | ❌ FY-unique *statutory* reference | `ref` is our document number, not a tax-invoice serial; no 16-character cap |
  | ❌ e-invoicing / IRN / signed QR | §7.9b does not apply to this module |

  ⚠ **ABOUT.md §5 currently says "the liability falls due on the RA bill, which
  is the tax invoice."** That sentence is now wrong about this module and must
  be corrected in the same commit as the code — an RA bill states what is
  claimed, and the tax invoice against it is a later, separate document.

  This is the single largest scope reduction against the original proposal and
  roughly halves the module.

---

## 6. Where this design falls short

Listed before you find them.

1. **[AMENDED — resolved] The hard block rejects the client's own rounding.**
   As measured in §0, two of their three historical over-claims are 0.5%
   site-measurement rounding. **Decided: build the hard block as specified, with
   no override anywhere in the UI**, and put the tolerance in a single named
   module constant:

   ```python
   OVERCLAIM_TOLERANCE = 0.0     # fraction of the approved quantity
   ```

   Three properties this constant must have, and they are the whole point:

   - **At `0.0` the behaviour is identical to a pure hard block.** No epsilon,
     no "close enough", no special case. Tested at both settings.
   - **It applies to the CUMULATIVE claim against the approved quantity,
     never per bill.** A per-bill tolerance of 1% across nine RA runs compounds
     to 9% and defeats the guard entirely — the tolerance would become the
     over-claim. Cumulative is the only place it can live without doing that.
   - **There is no UI for it.** Not a form field, not a query parameter, not a
     per-line tick box. Changing it is a deliberate edit to a constant with a
     comment beside it, which is the `REQUIRE_PO_FOR_WON` precedent (§9).

   Separately and *not* the same thing: the comparison rounds at **1e-6** to
   kill IEEE-754 noise, so that a cumulative of `12.000000000000002` from
   summing `1.1 + 2.2 + 8.7` is not reported as an over-claim of 2 femtometres.
   That is float-representation hygiene six orders of magnitude below the 2
   decimal places real quantities carry; it is not a commercial tolerance and
   it does not soften the block.
2. **The guard is on quantity only.** Because the RA rate can differ from the
   approved rate (10 cells do), a bill can be within quantity and still exceed
   the approved *value*. No value guard is proposed. On a project priced off a
   rate contract this is a real hole.
3. **[AMENDED — resolved] Deductions.** The record carries a **bill-level
   `deductions` list from day one**, empty in Phase 1, with the balance
   arithmetic and the printed document already accounting for it. Retention,
   mobilisation-advance recovery and cess all fit one shape:

   ```python
   {"code": "retention", "label": "Retention @ 5%",
    "basis": "percent" | "amount", "pct": 5.0, "amount": 62500.0}
   ```

   `amount` is **always stored**, computed from `pct × claim_subtotal` when the
   basis is a percentage, so the printed document never recomputes and a
   certified bill cannot change its own figures later — the same rule
   `supply_rate` follows on a BOQ line and `prior_invoiced` follows on a PI.

   `net_payable = claim_subtotal − deduction_total`, and that identity holds on
   every bill including the ones with an empty list.

   It is empty in Phase 1 because we do not yet know whether their certified
   bills carry retention. **An empty array now is cheap; retrofitting a
   deduction block after the print format exists is not** — every issued
   document would have been produced by a renderer that had no place to put it.
4. **No measurement sheet.** A claimed quantity is asserted, not substantiated.
   Real RA billing backs each figure with an abstract of measurements, which is
   what the client's engineer signs against.
5. **[AMENDED — step 1.5, resolved] The revision chain is matched on
   `item_no`.** It was, and it was wrong — not only across revisions but
   *within a single BOQ*, because `item_no` is not unique there either. The
   client's section A carries item `17` twice, item numbers restart per
   section, and the guard silently collapsed ten lines. Lines now carry an
   opaque `line_id` and both `approved_by_line()` and `claimed_by_line()` key
   on it. The renumbering restriction this entry worried about is withdrawn —
   see §4.
6. **Concurrency.** Two simultaneous RA creations against one BOQ can both read
   the same `max(ra_no)`. `STORE` is a plain dict with no lock (only `db._lock`
   guards sync), so this is a pre-existing property of the app shared by every
   `_next_ref()` in it, not something RA introduces. It has never bitten because
   the app is effectively single-user. Worth a note, not worth a lock yet.
7. **No void or cancel.** RA bills are proposed immutable and non-deletable,
   which is right for a claim that has been certified — but it means a mistake
   is corrected only by the next bill. Same shape of gap as §7.3, and the
   revision route does not help, because the error is in the claim rather than
   in the contract.
8. **One rate per line per RA.** The annexure has a single rate column per
   block, so this matches the data — but a part-quantity claimed at a varied
   rate cannot be expressed.

---

## 7. Decisions taken · 2026-08-05

Kept as the record of what was settled and why, so the next person does not
re-open them.

| Question | Decision |
|---|---|
| Tolerance on the over-claim block | **Hard block, no UI override.** `OVERCLAIM_TOLERANCE` defaults to `0.0`; applies to the **cumulative** claim only, never per bill. §6.1 |
| RA rate divergence from the approved BOQ rate | **Warn at entry, never block.** Stored on the claim row. §0.3 |
| Deductions | **In the record from day one**, empty in Phase 1, with the arithmetic and the print format already accounting for them. §6.3 |
| Is the RA bill a tax invoice? | **No.** Claim document only. No Rule 46, no place of supply, no e-invoicing, no `_tax_lines()`. §5 |
| `#VALUE!` on repeated header bands | **Out of scope.** Phase 3 import notes. §0.2 |

### Still open, deliberately

Everything else in §6 — the value guard (§6.2), measurement sheets (§6.4),
concurrency (§6.6), the absence of a void flow (§6.7) and one-rate-per-line
(§6.8) — is unresolved and recorded rather than solved.

### Step 1.5 · 2026-08-06 — the stable line identifier

Inserted between steps 1 and 2 after the `item_no` key was found to be
ambiguous inside a single BOQ, not merely across revisions.

| Question | Decision |
|---|---|
| What key does a claim match on? | **`line_id`** — opaque, server-minted (`uuid4().hex[:12]`), unique within one BOQ record. Not positional, not derived from any displayed field. §4, §6.5 |
| Uniqueness scope | **Within a BOQ record only.** Claims are already scoped to a parent BOQ, so a cross-record collision is harmless and there is no global registry. |
| What happens to a posted id | Well-formed and unused → kept verbatim. Missing → minted. Duplicated in one post → first kept, rest minted (a copy-pasted row). Malformed → minted, never echoed. |
| Existing records | `boq.backfill_line_ids()` via `tools/backfill_line_ids.py` — explicit, idempotent, fills blanks only. Claims predating the field are **counted, never guessed back**. |
| May a revision renumber? | **Yes**, now that the id carries the history. §4 rule 1 withdrawn. |
| May a revision delete a claimed line? | **No** — `boq.revision_blockers()`, naming the line and the RA numbers. Unclaimed lines delete freely. |
| The client's duplicate item 17 | **In their source workbook, left exactly as it is.** The seed is a faithful copy of their real schedule. The BOQ form gains a non-blocking amber band flagging repeated item numbers within a section. |
