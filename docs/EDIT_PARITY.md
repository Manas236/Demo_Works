# EDIT PARITY — what each document's edit form can change

> **STATE: BASELINE, measured on `5a060e7` (2 November 2026), before the
> "full editing on all documents" pass.** This file is rewritten to the final
> state in the same pass; the commit that adds it is the before-picture.
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

## Baseline table

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
