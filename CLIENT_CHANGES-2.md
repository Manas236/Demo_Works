# CLIENT_CHANGES-2.md — Phase 3

**Source:** client meeting, 19 August 2026 (Yogesh Bankar, Samruddhi Fire Services)
**Commercial:** quoted in MG/SF/2026-02 as Phase 3A / 3B / 3C
**Status:** not started. Nothing in this file is built.

**Authority:** MG/SF/2026-02 (3A / 3B / 3C) was **sent** and is **unsigned** as at
22 August 2026.

The **§0 gate in `CLIENT_CHANGES.md` applies to this file in full.** No item here
gets built until MG/SF/2026-02 is signed, or until a dated override block in
`CLIENT_CHANGES.md` §0 names the specific item. An override is a decision the
client-facing owner takes and records; it is never one an agent may take, infer or
extend.

**This file is a specification, not an instruction to build.** The build order below
applies *once work is authorised* — it does not authorise the work.

Phase 2 items live in `CLIENT_CHANGES.md`. This file is Phase 3 only.

---

## Build order is not negotiable

**3A → 3B → 3C.**

3B must land before 3C because attendance and measurement both need to know who is
logged in and who approved what. Building 3C first means retrofitting auth over it
afterwards, which is the expensive way round.

Within 3B, access control must land before approvals. An approval ladder with no
concept of a user is meaningless.

---

## Phase 3A — document and register changes

Small, self-contained, no new load-bearing invariants.

| # | Item | Notes |
|---|---|---|
| A1 | PO base rate editable | Straightforward field unlock. |
| A2 | Discount column on final PO | New column, flows into PO total. |
| A3 | Additional charge lines on final PO | See below — **do not build four fields**. |
| A4 | Total outstanding on client register | See caveat below. |
| A5 | Write-off / adjustment on a payment | See below. |
| A6 | RA edit and delete — **draft only** | See rule below. |

### A3 — additional charges: one repeater, not four fields

Client asked for loading & unloading, transportation, and "2 extra charges" as
separate items. That is one requirement, not four.

Build a **single additional-charges repeater** on the PO: label + amount, with the
heads seeded in `/settings` and editable by the client. Same pattern as the charge
heads already in `charge.py`.

Four hardcoded fields guarantees a fifth request within a month.

### A5 — write-off / adjustment on a payment

The problem: contractor allows a bill short (bills ₹1,00,000, allows ₹90,000). The
bill still says ₹1,00,000, receipts show ₹90,000, so ₹10,000 sits in outstanding
forever.

This field lets that ₹10,000 be written off so outstanding is correct internally.

**It is not a GST credit note.** It produces no document and has no number series.
The formal credit note is quoted separately as an option and is not in Phase 3A.

### A4 — outstanding caveat

Until the formal credit note exists, Total Outstanding is only as correct as the
write-off field makes it. This limitation is stated in MG/SF/2026-02 §6 deliberately —
do not quietly present the figure as authoritative.

### A6 — RA edit rule

**Edit and delete are allowed on DRAFT bills only.** An issued bill is cancelled and
reissued, never edited.

Reasons, all still binding:
- Issued bills are snapshots and feed `previous_balance` on the next bill
- `can_delete()` already refuses a bill carrying receipts
- GST requires consecutive invoice serials — you cannot edit a serial away

The client asked for "edit and delete in RA" without qualification. This narrowing is
deliberate and must be explained to him rather than silently applied.

**What is already built — a finding, recorded 23 August 2026. Not a commercial ruling.**
The draft / issued / cancelled lifecycle shipped on 15 August 2026 under
`CLIENT_CHANGES.md` item 3, and it brought **both** halves of what 3A.06 sells:

| Half of 3A.06 | Route | Function | Gate | State today |
|---|---|---|---|---|
| Cancel-and-reissue an **issued** bill | `GET,POST /ra/cancel/<id>` | `ra.cancel_ra()` | `ra.can_cancel()` — allows draft **and** issued, refuses cancelled, refuses a bill carrying receipts | **built** |
| **Edit** a **draft** bill | `GET,POST /ra/edit/<id>` | `ra.edit_ra()` | `ra.can_edit()` — refuses cancelled, refuses issued, refuses mid-chain via `claim_is_frozen()`; so it permits a **draft that is the latest bill on its BOQ** | **built** |
| **Delete** a **draft** bill | `GET,POST /ra/delete/<id>` | `ra.delete_ra()` | `ra.can_delete()` — refuses receipted, cancelled, issued, and any bill that is not the highest `ra_no` | **built** |

`ra_no` is never reused, so the consecutive-serial reason above is already held by
construction rather than by the narrowing.

⚠ **This is a fact about the code, not a decision about the money.** A6 is **not**
marked delivered, is **not** removed from 3A, and its price is **not** changed by this
note — those are the client-facing owner's to take, and 3A.06 as sold may still cover
work this table does not show. The obvious candidate is the **latest-bill-only**
restriction on both edit and delete: the client asked for "edit and delete in RA" without
one, and a draft that is not the highest `ra_no` is refused today. What an agent may
**not** do is build A6 from scratch without first reading these three routes.

---

## Phase 3B — users, access and approvals

This is the foundation phase. Everything here is load-bearing.

### B1 — user accounts and login

No authentication exists today. No users, no sessions, `SECRET_KEY` is still the demo
default.

`SECRET_KEY` must be moved to a real environment-supplied value as part of this work.
It is not a separate task.

### B2 — permissions are named strings, minted in code

- Permissions are **defined in code** (`ra.create`, `charge.approve`, `employee.view`, …)
- Roles are **bundles of permissions**, editable as data
- Users hold **one or more roles**; effective permissions are the **union**

The client can assign existing permissions to roles. The client **cannot invent new
permission strings** — a typo'd permission either silently grants nothing or makes a
route unreachable.

Rationale: Yogesh will change his mind about who can do what. Permissions in data means
that is a checkbox in `/settings`, not a code change and a deploy.

### B3 — Owner / Admin split

| Tier | Who | Can do |
|---|---|---|
| **Owner** | Manas | Everything. Defines what a role *means*. Undeletable. |
| **Admin** | Yogesh / a Director | Create users, deactivate users, assign existing roles. Cannot alter role definitions. |

- More than one Owner is permitted; only an Owner can create an Owner
- The last remaining Owner cannot be deleted or deactivated
- Password reset is manual (Owner action) — email reset is explicitly out of scope

This split exists so the client handles routine staff churn themselves — including
urgent access removal when someone is dismissed — without it becoming an unpaid
support call.

Disclosed to the client in MG/SF/2026-02 §10: a vendor administrator account is
retained and can be disabled at exit.

### B4 — roles as discussed

Director (×2), Operations Head, HR, Sales Manager, Purchase Manager, Accountant.

- HR information is restricted from Sales, Purchase and Accounts
- One user may hold several roles — the client explicitly wants Sales and Purchase linkable

### B5 — default deny, rolled out in audit mode

**Default deny is the rule.** A route with no declared permission is inaccessible, not
open. Otherwise every future feature ships wide open and nobody notices.

**Rollout is two-stage** so nothing breaks under users:

1. **Audit mode** — the decorator is applied everywhere but only *logs* what it would
   have refused. Run the app, run the suite. Every undeclared or wrongly-declared route
   surfaces in the log without blocking anyone.
2. **Enforce** — flip it once the log is clean.

Add an AST test asserting every route function declares a permission. Same technique as
`test_import_directions.py`.

### B6 — approvals

- **Charges:** three-step ladder — Director → Operations Head → HR, in sequence
- **RA / Tax Invoice / PO:** Operations Head + Director
- **Any one Director's approval is sufficient.** Confirmed by the client.

**Load-bearing rule:** a user cannot approve a record they created. This is checked
against the **record's creator**, not against the approver's role.

Without this, union permissions defeat the ladder — a user holding both Sales Manager
and HR could raise a charge and approve it themselves.

### B7 — unapproved documents are view-only

Original client wording was "cannot be printed or screenshoted". Screenshot prevention
is impossible; the client confirmed that line was a joke.

Real requirement: **an unapproved document may be viewed, but not printed or
downloaded.**

- Gate the print and download routes on approval status
- The view page needs a print stylesheet that blanks it, or `Ctrl+P` bypasses the gate

### B8 — file attachments

First feature that breaks the existing storage model. There is no `/static`, images are
base64 data URIs, and `MAX_JSON_BYTES` is 300,000. A photographed supplier bill is 2–5 MB.

Needs **real file storage** with a path held on the record, plus a size and type gate.

- **Charges:** attachment is **compulsory** (client requirement)
- **Payments:** attachment is **optional** — bank transfers often have no separate slip,
  and compulsory would block honest entries
- Deleting the parent record deletes its file. No orphans.

Vocabulary warning: "receipt" already means the payment record. What is attached to it
is a **proof of payment** (bank slip / cheque / UTR). Do not overload the word.

---

## Phase 3C — measurement, labour cost and project result

### C1 — order of working

Stated by the client, and it is the actual domain model:

```
BoQ → Delivery Challan → RA-Supply
BoQ → Measurement     → RA-Installation
```

Supply is proven by a delivery challan. Installation is proven by a measurement.

Today installation quantity is typed straight into the claim grid with nothing behind
it. C2 closes that.

### C2 — measurement document

Raised from the BOQ. Approved measurements become the source of installation quantity
on RA-Installation.

### C3 — merged RA

**Separate document type**, same relationship as Draft PO → PO.

What it is: RA-Supply and RA-Installation are still raised **separately**, each keeping
its own `ra_no` and status. The merge produces a single document carrying **both sets of
line rows stacked**, with one combined total, raising **one tax invoice number**.

Client's own example:
```
RA-Supply       : Item 1 (qty 1)  ₹500
RA-Installation : Item 1 (qty 1)  ₹700
Merged          : Item 1 (qty 1) + Item 1 (qty 1) = ₹1,200
```

**Invariants:**

- The merged record **never holds claims of its own.** It references the two source
  bills. Copying claim rows into it would make the over-claim guard count the same
  quantity twice.
- Totals are the **sum of the two bills' own stored totals**, never recomputed from the
  live BOQ. Same defect class as the `print_ra` bug already fixed once.
- A bill may appear in **at most one live merged document.** Otherwise the same money is
  invoiced twice.
- A source bill inside a live merged document **cannot be cancelled.** Cancel the merged
  document first, which releases both legs.
- **Receipts stay attached to the source bills.** The merged document derives its
  balance by summing them. Do not repoint receipts — it would churn
  `previous_balance()` and the memo line for no gain.
- Per-line HSN/SAC already supports supply and installation carrying different GST
  rates, so the stacked tax block foots correctly with no new work.

Build the merge action **on the RA register from day one**. The draft-PO → PO bridge was
initially shipped without its entry point; do not repeat that.

### C4 — employee master

Employee details and salary.

### C5 — attendance and site-wise labour cost

- Presentee / absentee, recorded **daily**
- Salary as 0 or 1 based on attendance
- **One employee = one site = one day**
- OT = (salary ÷ 8) × hours
- Presentation table: Employee — Site — OT time

**This is a labour cost tracker, not payroll.** It feeds project costing. Statutory
matters — PF, ESIC, professional tax, minimum wages — are the client's responsibility
and this is stated in MG/SF/2026-02 §5.

**The OT multiplier is a configurable setting, not hardcoded.** The client specified
salary ÷ 8 × hours, which is 1× ordinary rate. Statutory overtime under the Factories
Act and most state Shops & Establishments Acts is generally **twice** ordinary wages.
Hardcoding 1× would mean the software computed an underpayment. Default it to the
client's figure, but make it changeable.

### C6 — project profit and loss

Planned margin from the BOQ against actual cost from purchase orders and recorded
charges, with the difference shown.

**Double-count trap:** attendance-based wages and the installation base rate both
represent labour. Subtracting both counts labour twice. Decide which is authoritative
before wiring C5 into C6.

---

## Already built, not in Phase 3

Delivered at no charge and listed in MG/SF/2026-02 §3. The Phase 3C foundation partly
rests on these:

- Employee / miscellaneous charges module (`charge.py`, editable heads in `/settings`)
- Project grouping / project entity
- Draft PO → PO bridge

Note the project **entity** is built; the project **P&L view** (C6) is not.

→ The Draft PO → PO bridge is **F.05** of MG/SF/2026-02 section 3, and recording it here
as delivered-no-charge is authorised by the **23 August 2026 "SUPERSEDED IN PART"** block
in [CLIENT_CHANGES.md](CLIENT_CHANGES.md) §0 — which spends the 16 August prohibition for
**that route only**. The **BOQ → PO** route (`/purchase/from-boq/<id>`) is in no
quotation, is deliberately **not** on the list above, and the 16 August prohibition
stands for it in full. Do not add it here.

---

## Stated by the client, NOT in MG/SF/2026-02 — unpriced and untagged

⚠ **Neither scope nor exclusion. These five have no home yet, and that is the whole
point of this section.** Each was said by the client at the 19 August 2026 meeting, and
each is absent from **both** this file's 3A / 3B / 3C tagging **and** the sent quotation.

| # | What he said | Status |
|---|---|---|
| 1 | Director — **visual dashboard** | Not tagged. The phrase "visual dashboard" appears nowhere in MG/SF/2026-02. |
| 2 | Operation Head — **visual dashboard** | Not tagged. Same absence. |
| 3 | HR — **salary editing, inside employee details** | Not tagged. HR editing salary appears nowhere in MG/SF/2026-02. C4 covers an employee master carrying salary; it does not cover HR's right to edit it. |
| 4 | Accountant — **overview of employees** | Not tagged. An Accountant employee overview appears nowhere in MG/SF/2026-02. |
| 5 | Accountant — **manage employees and their site** | Not tagged. Appears nowhere in MG/SF/2026-02. B4 names the Accountant role; it does not give that role employee management. |

**None of the five is inside the 3B or 3C price.** MG/SF/2026-02's scope-and-changes
clause fixes prices to **tagged references only**, and not one of these carries a tag.
Building any of them inside Phase 3 would be **unpaid work** — however natural it looks
sitting next to the roles (B4) and the employee master (C4) that *are* tagged.

**Dropping them silently is equally wrong.** He said them in a meeting, they are in his
own requirements list, and he will expect them. They are recorded here precisely so that
neither mistake happens by accident: they are not quietly built, and they are not quietly
forgotten.

**Items 1 and 2 need a client ruling before they can be priced at all.** A dashboard
already exists in this software (`dashboard.py`). Whether "visual dashboard" meant *that
dashboard, restricted by role* or *a new analytics view* is **not answerable from any
document we hold**, and the two differ by an order of magnitude in cost. Ask him. Do not
take the cheaper reading because it is cheaper, and do not take the dearer one because it
is safer.

**Not priced here, not built here, and not added to any phase.** Putting any of these
five into 3A, 3B or 3C would be exactly the silent inclusion this section exists to
prevent.

---

## Excluded

- Formal GST credit note — quoted separately as an option, not in 3A
- E-invoicing / IRN — excluded; quoted separately if the turnover band brings it in
- Retention and mobilisation advance recovery — excluded unless figures arrive before
  3A commences
- Password reset by email
- Screenshot prevention — impossible, and withdrawn by the client

---

## Open questions for the client

1. ✅ **CLOSED — 23 August 2026. No longer a question for the client.**
   ~~Does the merged RA carry **one tax invoice number covering both bills**? Their paper
   practice already runs Tax Invoice No and RA Bill No as separate series, which
   suggests yes — but confirm before building C3.~~

   **Answered by commitment rather than by the client.** MG/SF/2026-02 **3C.02** — sent
   21 August 2026 and read by him — sells the merged RA as supply and installation bills
   raised separately and then combined into one document carrying both sets of lines
   **and one tax invoice number**, stated as delivered scope and not as a question.
   Putting it to him now would be asking permission for something we have already sold
   him. The C3 invariant above is unchanged and is now backed by a commercial commitment.

   ⚠ **The problem underneath did not disappear — it moved.** It has stopped being a
   client question and become a **build** question: BQ1 below.
2. Is a payment ever received against a **merged document** rather than an individual
   bill? Current design says no.
3. GST head and place of supply — required before go-live.
4. Which is authoritative for labour cost in C6: attendance wages or the installation
   base rate?

---

## Open build questions — ours, not the client's

⚠ **Do not put these to the client.** They are consequences of what has already been
sold to him, and they are settled by a design pass here.

### BQ1 — C3: one merged invoice number against "the RA bill is the tax invoice"

[DOMAIN.md §4](DOMAIN.md) rules that an RA bill **is** a tax invoice, and §4.2 that its
**Tax Invoice No. is its own statutory series** — the seller's serial across all work,
counted independently of `ra_no` and never derived from it. 3C.02 now commits us to a
merged document minting **one tax invoice number** across two source bills that each
already carry one — a third serial raised over two already spent. The consecutiveness A6
leans on ("GST requires consecutive invoice serials — you cannot edit a serial away", the
stated reason an issued bill is cancelled and reissued rather than edited) has a hole in
it until something decides which of the three numbers is the statutory invoice and what
becomes of the other two.

*One fact that changes the shape of the fix rather than removing it:* per
[STATE.md §2.1](STATE.md) the tax invoice number is **not yet a generated series** —
`tax_invoice_ref` is a typed field on the RA record. So the collision today is between a
typed value and a minted one, and C3 would be the first thing in this app to mint one.

**Recorded, not solved.** Solving it is a C3 design pass and it must happen **before** C3
is built. Do not resolve it inside a build step, and do not resolve it by quietly having
the merged document reuse one leg's number.

---

## Security items promoted by this phase

These were previously acceptable because the threat model was "three trusted staff, no
adversary". Role-based access makes an **authenticated insider** the threat model, and
they become blockers:

- Unescaped output in `product.py` and `quotation.py` — a stored XSS lets one user
  hijack another's session and approve their own submissions
- `SECRET_KEY` demo default — session forgery

Both are **narrow security fixes**, which the `product.py` / `quotation.py` freeze
explicitly permits (precedent `9d060ee`). Fix them inside 3B. No separate quotation line.
