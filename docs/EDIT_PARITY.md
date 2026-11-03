# EDIT PARITY — what each document's edit form can change

> **STATE: FINAL, 2 November 2026** (the full-edit pass). The baseline
> measured on `5a060e7` before the pass is kept below it for comparison.
>
> Read from the code, route by route (`grep '@.*route("/edit'`), not from a
> plan. "yes" = the edit route changes it today; "no" = it does not, or there
> is no edit route at all; "n/a" = the document has no such thing on create
> either. A status column names the statuses in which the edit route opens.

## The definition being measured against

The edit form IS the create form, prefilled from the stored record: every
header field, the party (address book + free text, as create offers), dates,
terms/notes, project, every line column, add (from every source create
offers) / remove / reorder lines, the round-off tick, the number (forward
only). Cancelled = locked. After issue every change is logged with the
screen-only band. The only allowed locks are the five ledger locks
(CLIENT_CHANGES.md §0, 2 Nov 2026 block).

## FINAL table — 2 November 2026, after the full-edit pass

> Measured from the code at the end of the pass. "yes" = the edit route does
> it; **L1–L5** = one of the five allowed ledger locks; "n/a" = create has no
> such thing either (the edit form IS the create form, so parity is with
> create). Every other cell is yes. Four cells are **declared** rather than
> yes or n/a — see "Declared, not built" below; they are the honest residue.

| Document | Opens in | Party | Dates | Terms / notes | Project | Line sources on edit | Add | Remove | Reorder | Every column | Round-off | Number (forward) | After-issue log + band |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Purchase order | all but Cancelled | yes (address book, as create) | yes | yes | yes (BOQ order follows its schedule) | own BOQ (`line_id`, qty left to order), BOQ items, Spec library, free text, extra parts, Excel | yes | yes (L4: nothing per-line received is tracked, so no lock) | yes | yes (8-digit HSN) | yes | yes | yes (rate moves also in `reprice_log`) |
| Work order | all but Cancelled | yes | yes | yes (site, T&C) | yes | free text, headings, Excel | yes | yes | yes | yes (both rates, GST %) | yes | yes | yes |
| BOQ | always | yes | yes | yes | yes | Spec library, free text (the create editor) | yes | yes — **L2** for a claimed line | yes | yes — **L2**: qty not below the live claim | yes | yes (root; revisions follow) | yes (every edit) |
| Delivery challan | always | yes | yes | yes | n/a | BOQ picker, Excel | yes — **L3** if billed | yes — **L3** if billed | n/a (schedule order, as create) | qty — **L3** if billed | n/a | yes | yes |
| Proforma invoice | always | yes (typed, as create copies it) | yes | yes | yes | parent quotation / BOQ lines, Excel, free text | yes | yes | yes | yes | yes | yes | yes |
| Tax invoice (standalone) | not cancelled | yes | yes (inside FY) | yes | n/a | parent proforma / BOQ lines, free text | yes | yes | yes | yes | yes | **L5** | yes — needs `invoice.edit_issued` |
| Tax invoice from an RA bill | issued bill | yes (text) | yes (inside FY) | yes | n/a | **L1** | **L1** | **L1** | **L1** | text only — **L1** | **L1** | **L5** | yes — needs `invoice.edit_issued` |
| Merged tax invoice | live | yes (text) | yes (inside FY) | yes | n/a | **L1** | **L1** | **L1** | **L1** | text only — **L1** | **L1** | typed on create; **L5** after | yes — needs `invoice.edit_issued` |
| Quotation | always | yes (address book + typed) | yes | yes | n/a | Spec library, Excel, free text | yes | yes | yes | yes | yes | yes | yes |
| Product inquiry | always (converted too) | yes | yes | yes | n/a | BOQ lines (as text), free text, spec row | yes | yes | yes | yes (no rate — standing ruling) | n/a | yes | yes once converted |
| Measurement sheet | not approved ¹ | n/a | yes | yes | n/a | BOQ picker | yes | yes | n/a (schedule order) | qty, grid | n/a | yes | declared ² |
| Receipt | always | n/a | yes | yes | n/a | n/a | n/a | n/a | n/a | yes | n/a | yes | declared ² |
| RA bill (draft) | draft + latest | n/a | yes | yes | n/a | BOQ / DC / MS (as create) | yes | yes | n/a (schedule order) | qty / rate | yes | yes (RA number) | n/a (draft) |
| Payslip (draft) | draft | n/a | n/a | n/a | n/a | muster (derived — CLAUDE.md: Basic/OT only from `attendance.month_figures()`) | n/a | n/a | n/a | allowances / statutory | yes | n/a | n/a (draft) |
| Charge | not approved ¹ | yes | yes | yes | yes | n/a | n/a | n/a | n/a | yes | n/a | n/a | n/a |

¹ **Not a lock this pass added.** CLAUDE.md's standing rule: *"a decision
already taken (APPROVED / REJECTED) is never overturned"* (`approval.can_modify()`).
The ladder is switched off, so only records approved before 12 Sep 2026 are
affected (ABOUT.md §7 gap 108's shape). Declared, not overridden.

² A receipt and a measurement sheet carry no issued state; their edits are
not logged. Declared (§0 block, call 11).

## Declared, not built (the honest residue)

* **Excel onto the measurement sheet's EDIT form** — create imports the joint
  grid; edit does not yet (ABOUT.md §7 gap 110).
* **Product inquiry lines added from the BOQ on edit arrive as text** — the
  inquiry's parser re-mints any `line_id` not already on the draft (pinned by
  `test_a_posted_line_id_that_is_not_on_this_draft_is_re_minted`), so such a
  line is not linked to the schedule (gap 111).
* The two footnoted columns above.

## Baseline table — on 5a060e7, before the pass

Line sources: **B** = BOQ picker, **S** = Specification library, **X** =
Excel import, **F** = free text, **C** = copied from the parent document.

| Document | Edit route | Opens in | Party | Dates | Terms / notes | Project | Line sources on create | Add line on edit | Remove | Reorder | Every column | Round-off | Number | After-issue log + band |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Purchase order | `/purchase/edit/<id>` (**reprice screen**) | every status but Cancelled | **no** | **no** | **no** | yes (not a BOQ PO) | B S F X (create); B (from-BOQ); C (from-inquiry) | **extra parts only (F)** | **extra parts only** | **no** | **rate, disc, make, HSN only** — no qty, no description, no unit | yes | Draft only | **no** (reprice_log only; no band) |
| Work order | `/wo/edit/<id>` | **Draft only** | yes | yes | yes | yes | B F X | yes | yes | **no** | yes | yes | **no** | **no** (not editable after issue) |
| BOQ | **none** (revision via `/boq/create?revise=`) | — | **no** | **no** | **no** | **no** | S F X | **no** | **no** | **no** | **no** | **no** | **no** | **no** |
| Delivery challan | `/dc/edit/<id>` | every status | yes | yes | yes | n/a | B | **no** | **no** | **no** | **no** (lines locked) | n/a | **no** | yes |
| Proforma invoice | `/proforma/edit/<id>` | always | yes | yes | yes | yes | C X | yes (F, X) | yes | yes | yes | yes | yes (forward) | yes |
| Tax invoice (standalone) | `/invoice/edit/<id>` | not cancelled, not approved | yes | yes (inside FY) | yes | n/a | C | yes (F) | yes | yes | yes | yes | locked (lock 5) | yes |
| Tax invoice from an RA bill | `/ra/edit-text/<id>` | issued bill | yes (text) | yes (inside FY) | yes | n/a | C | lock 1 | lock 1 | lock 1 | text only (lock 1) | lock 1 | locked (lock 5) | yes |
| Merged tax invoice | `/merged/edit/<id>` | live | yes (text) | yes (inside FY) | yes | n/a | C | lock 1 | lock 1 | lock 1 | text only (lock 1) | lock 1 | **no** (not typeable on create either) | yes |
| Quotation | `/quotation/edit/<id>` | always | yes (typed fields; **no address-book picker on edit**) | yes | yes | **no** | S (spec picker) F X | F only (**no S, no X**) | yes | yes | yes | yes | **no** | yes |
| Product inquiry | `/po/edit/<id>` | unconverted only | yes | yes | yes | n/a | B F | yes | yes | **no** | yes (no rate box, by ruling) | n/a | **no** | n/a (not "issued") |
| Measurement sheet | `/measurement/edit/<id>` | not approved | n/a | yes | yes | n/a | B | yes (B) | yes | n/a (schedule order) | qty | n/a | **no** | **no** |
| Receipt | `/receipt/edit/<id>` | always | n/a | yes | yes | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **no** | **no** |
| RA bill (draft) | `/ra/edit/<id>` | draft + latest | n/a | yes | yes | n/a | B / DC / MS | yes | yes | n/a (schedule order) | qty / rate | yes | **no** | n/a (draft) |
| Payslip (draft) | `/payroll/slip/<id>/extras` | draft | n/a | n/a | n/a | n/a | muster | n/a | n/a | n/a | allowances / statutory | yes | n/a | n/a |
| Charge | `/charge/edit/<id>` | not approved | yes | yes | yes | yes | n/a | n/a | n/a | n/a | yes | n/a | n/a | n/a |

## Gaps this pass exists to close

Every bold **no** above that is not one of the five ledger locks.
