# DOMAIN — the business this system serves

> **This file owns:** the business domain in plain language. What a BOQ is, how
> item numbering works, what the supply/installation split means, what running
> account billing is, how certification behaves, the tax-invoice requirement,
> the documents their business uses that this system does not have, and the
> principle governing the client's imperfect data.
>
> **This file does not own:** record shapes, function behaviour, module
> boundaries or any other code fact (→ [ABOUT.md](ABOUT.md), §3 for shapes).
> Nor the work queue, phase state, or what to build next
> (→ [STATE.md](STATE.md)). Where a rule below is enforced in code, this file
> cites the file and line rather than restating the implementation.
>
> **Read this before touching `boq.py` or `ra.py`.** Every guard in those two
> modules exists because of something in here, and a guard whose reason you do
> not know is a guard you will "simplify".

---

## 1. The business

Samruddhi Fire installs fire-protection systems — sprinkler networks, hydrant
lines, pumps, panels — into buildings under construction.

They are a **subcontractor**. They do not deal with the building's owner. They
are engaged by a **main contractor**, the firm running the whole construction
site, who engages dozens of trade subcontractors and coordinates them. The main
contractor receives Samruddhi's claims, decides what to allow, and pays.

That relationship shapes everything below. Samruddhi does not simply sell goods
and invoice them. They agree a priced schedule up front, execute it over months,
and claim progressively against it — and somebody else rules on every claim.

They run **several projects at once**. Sites observed in the client's own
documents include Bangalore, Ulwe and Wada. A site is therefore a **first-class
field on a project record, not a display label**, and code that assumes one
active project at a time is wrong about this business.

---

## 2. The BOQ — Bill of Quantities

**A BOQ is the priced schedule of one project, agreed before work starts.**

It is a list — commonly one hundred to two hundred lines — of every item of work
to be done, each with a quantity and a price. It is the contract's commercial
core. Once agreed, it is the document every later claim is measured against.

Nothing may be billed that is not on it. That single sentence is the reason the
over-claim guard (§3.4) exists and is hard.

### 2.1 Sections

A BOQ is grouped into **sections** — A, B, C — each being a system or an area of
work, each with its own subtotal. The client's seeded schedule has three.

Sections are not cosmetic. Item numbering and area columns are both scoped to
the section, not to the document (§2.2, §2.3).

### 2.2 Hierarchical item numbering

Lines are numbered `1`, `2`, `3` … and a line may have **children**: `24` with
`24.a` through `24.i` beneath it.

The relationship is a **specification hierarchy**, and it works like this:

- The **parent** — item `24` — carries the written specification. A paragraph of
  text describing the material, the standard it conforms to, how it is to be
  installed. **It carries no quantity and no rate.** It is a heading with legal
  weight, not a billable line.
- The **children** — `24.a` … `24.i` — are that same specification at different
  **sizes**, typically pipe diameters. Each carries its own quantity, its own
  rate, and its own amount. These are the lines that get billed.

So one specification paragraph can generate nine priced lines. A schedule of 97
lines might hold only 87 that are billable at all.

> **This is not a bill of materials.** A parent is not assembled from its
> children. Nothing is "made of" anything. The parent says *what kind of thing
> this is*; the children say *at which sizes, how much*. Code that treats this
> as component nesting will be wrong in ways that surface late.

#### `item_no` is a display label. It is never a key.

This is the subtlest correctness constraint in the system and it must not be
weakened.

Item numbers are **not unique**, for three independent reasons:

1. **They restart per section.** Item `4` exists in section A and again in
   section B. They are different lines.
2. **They repeat within a single section.** The client's own section A carries
   item **`17` twice** — on a flexible sprinkler drop and on a 150 mm butterfly
   valve, two genuinely different products whose rates are roughly eight times
   apart. This is in **their source workbook**. It is not a data-entry error
   introduced here, and it is not to be corrected (§6).
3. **They are edited.** Item numbers get renumbered when a schedule is revised.

On the real seeded BOQ, 87 priced lines carry only **77 distinct item numbers**.

Keying the over-claim guard on `item_no` collapsed the colliding lines
last-write-wins. Measured on the client's actual schedule, that waved through
**₹1,99,122.50 of over-claim** and wrongly refused **₹84,071.00 of legitimate
claim** — and the guard's verdict changed if you merely reordered the BOQ's
lines.

**Therefore every line carries `line_id`** — opaque, server-minted, unique
within a BOQ record, never shown, never printed, never derived from anything a
user can edit. Minted at [boq.py:291](boq.py#L291), validated at
[boq.py:296](boq.py#L296). A claim matches on it and on nothing else.

A **positional index** was considered and rejected: inserting a line
re-attributes every claim below it.

`item_no` remains the label a human reads, everywhere, and is forced to a string
at [boq.py:235](boq.py#L235) — the client's workbooks store item 4.1 as
`4.0999999999999996`, and seventeen digits of binary noise printed beside a
quantity somebody is paid against is not acceptable.

### 2.3 Area and floor columns, declared per section

A line's quantity is usually **broken down by where it is installed** — by floor,
by zone, by building. 700 metres of pipe is not 700 metres in one place; it is
some on the external run and some on level zero.

**Which columns exist is declared by the section, not by the document.** In the
client's workbook, section A declares `External` and `L0`; section B declares
`T1`; section C declares none at all.

Two consequences:

- A line's area breakdown may only use its **own section's** columns.
- A section may declare **no areas**, and then the line's total quantity stands
  alone with nothing to reconcile against. This is valid and must not be
  treated as missing data.

### 2.4 The supply/installation split

**Every BOQ line is priced twice**, on two independent tracks:

| Track | What it pays for |
|---|---|
| **Supply** | Delivering the material to site. Buying the pipe. |
| **Installation** | Fixing it in place. Labour, brackets, welding, testing. |

Each track has its own rate and its own amount. They are billed **separately and
at different times** — the pipe arrives months before it is all installed — which
is why RA bills alternate between them (§3.2).

**A line may carry one track only.** Section C in the client's schedule is
installation-only. Four lines in section B are priced at nil — a real quantity,
no rate, amount zero — and are valid. **Never assume both tracks are populated.**

### 2.5 Rates: a base rate plus an escalation

A rate is usually derived: a **base rate** from an agreed rate contract, plus an
**escalation percentage**.

These schedules are commonly priced off a rate contract agreed on a *different*
project — the client's own sheet is headed "Mohali Rates" — and then escalated
for this one. What the base column is called is therefore per-BOQ data, not a
constant.

Two facts that look like bugs and are not:

- **The final rate is stored as entered, not recomputed.** On a dozen lines of
  the client's own sheets the agreed rate deliberately differs from
  `base × (1 + escalation)` — a negotiated exception. Reporting that
  disagreement is reasonable; silently resolving it is not.
- **A missing base rate is not zero.** It means the rate was negotiated directly
  rather than escalated — the `-` in their cell. Rendering it as 0 would state
  that the material is free.

### 2.6 Revisions

The approved schedule sometimes genuinely changes: scope grows, an item is
added. That is a **revision** — a new BOQ record superseding the old one, never
an edit of the old one.

It must be a new record because RA bills are measured against a *specific*
revision, and a claim already submitted must not have its basis move underneath
it.

Because `line_id` carries a line's identity across revisions, **a revision may
renumber freely**. What it may not do is **delete a line that already carries a
claim** — that would leave a submitted claim with no approved quantity behind it
and nothing to hold the balance arithmetic. Refused at
[boq.py:690](boq.py#L690), naming the line and the RA numbers that claimed it.
Deleting an unclaimed line is free.

---

## 3. RA billing — the running account

**An RA bill is a claim for work completed so far.**

"Running account" means exactly what it says: an account that runs for the life
of the project. Every month or so, Samruddhi measures what has been built,
claims for it, and the balance carries forward. The client's own annexure is
**nine RA bills against one 97-line schedule.**

The cycle, per bill:

1. Site staff measure what was executed this period.
2. For each BOQ line, a quantity is claimed at a rate, giving an amount.
3. The bill goes to the main contractor.
4. He **certifies** it — allowing all, some, or none of each line (§3.5).
5. The next bill starts from what has cumulatively been claimed.

### 3.1 What a claim is measured against

Two different questions, answered by two different functions:

| Question | Answer | Reads |
|---|---|---|
| How much was approved for this line? | `approved_by_line()` [ra.py:306](ra.py#L306) | the **latest** revision — a revision exists precisely to change what is approved |
| How much has already been claimed? | `claimed_by_line()` [ra.py:385](ra.py#L385) | **every bill across the whole revision chain** |

The second is the subtle one. If claims were summed only against the current
revision, issuing a revision would reset every line's claimed quantity to zero
and the over-claim guard would stop guarding anything.

### 3.2 Legs, and why bills alternate

Because supply and installation are separate tracks (§2.4), each bill claims
**one leg only** — either supply or installation, never both.
[ra.py:80](ra.py#L80).

The client's real run alternates:

| Leg | Bills |
|---|---|
| Supply | RA 1, 2, 3, 5, 7, 9 |
| Installation | RA 4, 6, 8 |

**That is one number series whose bills happen to alternate, not two interleaved
series.** RA4 is the fourth bill on the project; it is not "installation bill
number 1". Getting this backwards produces two counters where the client has
one, and the client's own numbering stops matching.

The leg belongs to the **bill**. A claim row has no leg field at all, so a
mixed-leg bill has no shape it could be expressed in — a stronger guarantee than
a form that merely discourages one.

### 3.3 Cumulative claims

**A claim is cumulative across bills.** The question the guard asks is never
"is this bill's quantity reasonable" but "**does everything claimed against this
line, across every bill ever raised, exceed what was approved?**"

Each bill therefore carries, per line: what was approved, what was claimed
*before* this bill, what is claimed *now*, and what remains. Those four columns
are what make it a running account rather than an invoice.

**Those figures are frozen when the bill is issued.** RA3 stated a balance that
was true on its date. Raising RA5 must not rewrite a document the main
contractor has already been given.

### 3.4 The over-claim guard

**The cumulative claim on a line must not exceed the approved quantity.**

Catching this is the single thing the system was built to do. The client's live
spreadsheet has three lines already billed into negative balance:

| Item | Approved | Claimed | Over by |
|---|---|---|---|
| 4.2 | 12 | 12.06 | 0.5% |
| 24.c | 12 | 12.06 | 0.5% |
| 24.d | 35 | 46.54 | **33%** |

Two are site-measurement rounding on a pipe run. One is a real over-claim. A
hard block at the approved quantity rejects all three, and that was the decision
taken: **hard block, no override anywhere in the interface.**

`OVERCLAIM_TOLERANCE` [ra.py:102](ra.py#L102) is the only dial, defaults to
`0.0`, and has no user interface of any kind. When non-zero it applies to the
**cumulative** claim, never per bill — a 1% per-bill allowance compounds across
nine bills into roughly the over-claim it exists to prevent.

Separately, and **not** a commercial tolerance: a `1e-6` epsilon
[ra.py:109](ra.py#L109) exists so that summing `1.1 + 2.2 + 8.7` to
`12.000000000000002` is not reported as an over-claim of two femtometres. Six
orders of magnitude below the two decimal places real quantities carry.

**The guard reads claimed quantity and never a certified one.** What the main
contractor allows is his ruling, not a validation input.

### 3.5 Certification, and why it arrives out of order

The main contractor reviews a bill and **certifies** it: for each line, the
quantity and rate he is willing to allow. He may allow less than claimed. His
figure, not ours.

**Certification lags, and it lags unpredictably.** RA3 can come back certified
after RA6 has already been raised and submitted. This is normal in construction
and is not an edge case to be designed away.

Three rules follow, and each is load-bearing:

1. **A claim freezes; a certificate never does.** The claim on a bill is
   editable only while it is the latest bill for its BOQ — editing a mid-chain
   claim would silently change every downstream balance, including ones already
   printed and handed over. The certificate is editable **always**, including on
   a frozen bill, because otherwise it would be unusable exactly when it is
   needed. Gate at [ra.py:972](ra.py#L972); the certification writer at
   [ra.py:926](ra.py#L926) touches only the certified fields, so certifying can
   never reopen a claim.
2. **Uncertified is not zero.** A blank means *not yet ruled on* and is excluded
   from certified totals entirely, reported as "n of m certified". A certified
   quantity of **0.0 is a ruling** and does count. Collapsing the two
   under-reports what is owed — the exact inverse of the error this system
   exists to catch.
3. **Certifying more than was claimed warns, never blocks.**

### 3.6 An RA rate may differ from the BOQ rate

On ten cells of the client's real annexure, the rate claimed is not the approved
rate. Rates legitimately move on approved variations.

So a claim **stores its own entered rate**, and divergence from the approved
rate **warns at the moment of entry and never blocks**. A rate silently
disagreeing with the approved BOQ is one of the two failure modes this system
was sold to catch, so it must be visible while it is being typed rather than
discoverable afterwards.

### 3.7 Deductions

A certified bill may have amounts withheld before payment:

- **Retention** — a percentage held back on every bill until the project
  completes and the defects period passes. Standard practice; it is the main
  contractor's security against bad work.
- **Mobilisation advance recovery** — money advanced at the start of the project
  to get equipment on site, clawed back in instalments.

The record carries a bill-level deductions list, and **it is empty**. The
client's observed bill shows neither retention nor advance recovery. It stays in
the shape and stays empty until they confirm otherwise — **do not populate it
speculatively and do not remove it.** Retrofitting a deduction block after a
print format exists means every document already issued came from a renderer
with nowhere to put it.

---

## 4. REQUIREMENT — the RA bill is a tax invoice

> ⚠ **This is a requirement, not a description — and it is now PART BUILT.**
> The banner that stood here until 23 August 2026 read *"None of it is
> implemented"*. That was true when §4 was written and had stopped being true by
> 15 August 2026: most of this section shipped, and a reader taking the old
> banner at face value would conclude the merged RA (`CLIENT_CHANGES-2.md`
> 3C / **3C.02**) has a clean field to build on. It does not.
>
> **Every obligation below now carries a STATUS marker.** `shipped`, `part`, or
> `not built`. The marker records only what the code does today; **the
> requirement's own wording is unchanged and is not the marker's to move.**
> Where the two disagree the code is right and this file is stale
> ([INTRODUCTION.md §5.6](INTRODUCTION.md)) — report it, do not edit the code
> to match.
>
> **Nothing marked `part` or `not built` may be built without an approved plan.**
> The queue is [STATE.md](STATE.md) §2.1, which owns where each piece landed;
> this file owns why each is required.

The client's real as-submitted RA bill was obtained on **8 August 2026**. It is
headed **"TAX INVOICE"**.

The code currently asserts the opposite. `ra.py`'s own docstring
([ra.py:14-22](ra.py#L14-L22)) states that an RA bill is not a tax invoice, and
`test_ra_does_not_pull_in_the_tax_machinery`
([tests/test_ra_record.py:171](tests/test_ra_record.py#L171)) enforces it by
parsing `ra.py`'s AST, with a deliberate control test at
[tests/test_ra_record.py:185](tests/test_ra_record.py#L185) proving the check
can actually fail.

**That assertion must be inverted — asserting the tax block is present — not
deleted.** A deleted assertion pins nothing; an inverted one keeps proving that
the module is what it is supposed to be.

**STATUS — shipped.** Inverted on 15 August 2026, not deleted, and split
per-assertion exactly as §4.9 requires: `test_ra_carries_tax_invoice_record_shape`
([tests/test_ra_record.py:188](tests/test_ra_record.py#L188)) now requires the
tax block, and `test_ra_forbids_improper_tax_coupling`
([tests/test_ra_record.py:198](tests/test_ra_record.py#L198)) still forbids
`_tax_lines`, `invoice.py` and the e-invoicing tokens. `ra.py`'s docstring
([ra.py:14-17](ra.py#L14-L17)) now states the opposite of what it stated when
this section was written.

⚠ **The three paragraphs immediately above this marker are written in the
present tense and are now stale** — the code no longer "currently asserts the
opposite". They are left exactly as they stand because a requirement's wording
is not a status pass's to edit; the correction is this marker. Recorded in
[STATE.md](STATE.md) §6 as backlog.

### 4.1 What their real document carries

The third column is the **STATUS marker** described in the banner. It records
what `/ra/print` does today; it does not alter what the row requires.

| | | STATUS |
|---|---|---|
| Title | `TAX INVOICE` | **shipped** — [ra.py:3767](ra.py#L3767) |
| **Two number series** | a Tax Invoice No (`SF-3`) **and** an RA Bill No (`2`) | **part** — both print side by side ([ra.py:3699-3702](ra.py#L3699-L3702)), but the Tax Invoice No. is a **typed** field, not a series. §4.2 |
| Parties | buyer's and seller's GSTIN, and **both parties' state** | **part** — both GSTINs and the **seller's** state ship ([ra.py:3516-3520](ra.py#L3516-L3520), [ra.py:3706](ra.py#L3706), [ra.py:3713](ra.py#L3713)); the **buyer's state is not printed at all** |
| Reference | the main contractor's **PO / Work Order number and date** | **shipped** — `po_ref` / `po_date`, [ra.py:3705](ra.py#L3705), [ra.py:3711](ra.py#L3711) |
| Site | the project site name | **shipped** — [ra.py:3719-3722](ra.py#L3719-L3722) |
| Per line | description, **HSN/SAC**, unit, quantity, rate, amount | **shipped** — [ra.py:3593-3603](ra.py#L3593-L3603). §4.4 |
| Tax | `CGST 9%` + `SGST 9%` on the total | **part** — the arithmetic ships per rate slab (`ra.tax_slabs`, [ra.py:1067](ra.py#L1067)); which **head** applies does not. §4.3 |
| Adjustment | an explicit **Rounding Off** line | **shipped** — `ra.compute_rounding_off` ([ra.py:991](ra.py#L991)), printed at [ra.py:3690-3691](ra.py#L3690-L3691). §4.5 |
| Foot | bank details, stamp, Authorised Signatory | **shipped** — [ra.py:3778-3781](ra.py#L3778-L3781) |

### 4.2 The two number series are not the same counter

A **Tax Invoice No** and an **RA Bill No** appear on one page and count
independently. `ra_no` is the **RA Bill No** — the bill's position in the
project's run. The tax invoice number is a **separate series** and must not be
derived from it.

They count differently because they answer different questions: the RA number
says which claim this is on this project; the tax invoice number is the seller's
own statutory serial across all work.

**STATUS — part, and this is the one to read before building 3C.02.** The two
series print side by side and are printed as independent
([ra.py:3695-3702](ra.py#L3695-L3702)). But **no tax-invoice series is minted
anywhere in this app.** `tax_invoice_ref` is a plain typed form field
([ra.py:2899](ra.py#L2899), [ra.py:2935](ra.py#L2935), stored;
[ra.py:3064](ra.py#L3064), [ra.py:3091](ra.py#L3091), edited) with no counter
behind it, and when the operator leaves it blank `print_ra()` falls back
`tax_invoice_ref` → `ref` → **a string built from `ra_no`**
([ra.py:3486](ra.py#L3486)). So on a bill with the field left empty the printed
Tax Invoice No. **is** derived from `ra_no`, which is the one thing this section
forbids. The prohibition holds for every bill where the field is filled and
fails silently on every bill where it is not.

⚠ **`CLIENT_CHANGES-2.md` BQ1 depends on this.** 3C.02 sells a merged document
minting **one** tax invoice number; there is nothing minting a first one yet.

### 4.3 CGST + SGST versus IGST is a stored determination, not a hardcoded comparison

India's GST splits into a central and a state component for a supply within one
state (CGST + SGST), and a single integrated tax across state lines (IGST).

**OBSERVED:** The client's RA2 bill charges CGST + SGST, and both parties are Maharashtra-registered while the site is in Bangalore. That is what their document actually does.

**UNCONFIRMED:** Whether that is the correct statutory treatment has not been verified. For works contracts on immovable property, the place of supply may instead follow the property's location, which would imply IGST. This is an open question for the client's accountant. Do not resolve it, do not encode either reading as law, and do not cite tax law as settled.

**THEREFORE:** The tax head is a **stored per-bill determination with a default**, NOT a hardcoded comparison of any two fields (such as party states or site location). A wrong default must be fixable as data by the user, rather than requiring a code change and a database migration.

**STATUS — part.** The *shape* is right and the *reach* is not. `tax_type` is
stored on the bill ([ra.py:2955](ra.py#L2955), [ra.py:3080](ra.py#L3080)),
defaults to `cgst_sgst`, and `ra._head_split()`
([ra.py:1041-1065](ra.py#L1041-L1065)) splits a rate across whichever head the
bill already carries and **decides nothing** — no comparison of party states or
site location exists anywhere, which is what this section demands. What is
missing is the user's half: **no form anywhere offers the choice**, so the
default is not in practice "fixable as data by the user" and every bill is
`cgst_sgst`. **Place of supply with its State code is absent from the document
entirely.** Pending the client's CA — [ABOUT.md §7](ABOUT.md) gap 15. Do not
encode a guess.

*(Note: [ABOUT.md §5](ABOUT.md) documents a different derivation for the existing tax-invoice pipeline, which defaults to the ship-to state and then the source quotation's bill_state. The two pipelines are not required to agree, and this divergence is deliberate and unresolved rather than an oversight.)*

### 4.4 HSN/SAC is a per-line field

HSN (goods) and SAC (services) codes classify what is being supplied, and the
tax authority requires them per line.

**It is storable on the BOQ line and snapshotted onto the RA claim row — exactly
as `item_no` already is** (§2.2). Snapshotted, because the document is a record
of what was sent: if the classification on the BOQ is later corrected, a bill
already submitted must keep printing what it printed.

**STATUS — shipped.** Stored per BOQ line as `supply_hsn` / `install_sac`
([boq.py:518-521](boq.py#L518-L521)), and snapshotted onto the claim row as
`hsn_sac` by leg, alongside `item_no` and never re-derived
([ra.py:1246-1263](ra.py#L1246-L1263)). ⚠ The seeded codes are **placeholders
assigned by category** — [ABOUT.md §5](ABOUT.md), the specification library.

### 4.5 Rounding off is an explicit line

Their bill carries a **Rounding Off** row. It is a stated adjustment on the face
of the document, not an incidental float artefact to be absorbed silently.

**STATUS — shipped.** `ra.compute_rounding_off()`
([ra.py:991-999](ra.py#L991-L999)) computes it to the nearest whole rupee and
stores the delta; the row prints only when it is non-zero
([ra.py:3690-3691](ra.py#L3690-L3691)). The identity
`grand_total == net_payable + tax_amount + rounding_off` is stated and held at
[ra.py:1155](ra.py#L1155).

### 4.6 The printed bill is sparse, but keeps its family structure

**Only claimed lines appear.** A bill does not reprint the entire schedule.

**But a parent specification line prints above its sub-items, with no quantity
and no rate** (§2.2). The hierarchy survives into the document even though the
parent is not itself billable — a reader must be able to see which specification
a claimed size belongs to.

**STATUS — shipped.** `print_ra()` iterates the **claim rows** only, so only
claimed lines appear; the live BOQ is consulted for exactly one thing, the
`parent_item_no` relation ([ra.py:3540-3552](ra.py#L3540-L3552)), and the header
emits as a `.row-assembly` carrying no quantity and no rate, spanned rather than
blank ([ra.py:3564-3581](ra.py#L3564-L3581)). The clause prints in full, never
truncated.

### 4.7 Print order is not entry order — and these are two separate rules

**Their bill's line order is not BOQ order.**

**The entry form's order deliberately is BOQ order**, because the operator works
from a site measurement sheet against item numbers, and rendering every line in
schedule order — including exhausted ones, greyed rather than hidden — is what
makes a mis-claim visible.

> **Do not harmonise these two.** They serve different people at different
> moments: one is a data-entry surface for the operator, the other is a document
> for the main contractor. Treat print order as its own concern. An agent that
> "fixes the inconsistency" by forcing one onto the other will break whichever
> it loses.

**STATUS — not built, and the two are currently NOT harmonised only by
accident.** The entry form's half ships: it renders every BOQ line in schedule
order, exhausted ones greyed rather than hidden
([ra.py:2156-2159](ra.py#L2156-L2159)). The print's half does not exist as a
concern — `print_ra()` emits the stored claim rows in stored order
([ra.py:3556](ra.py#L3556)), which is entry order, which is BOQ order. **There
is no print-order rule in the code to break**, so an agent adding one is adding
it, not fixing it. The prohibition above binds the day one is added.

### 4.8 Explicitly out of scope

**IRN, e-invoice JSON generation and GSTR-1 filing are not in scope.**

A printed GST invoice is not e-invoicing. E-invoicing means registering each
invoice with a government portal over an API and printing the identifier and
signed QR code it returns. **Do not build toward that API.**

**STATUS — held, and enforced.** Absent by assertion, not merely by omission:
`test_ra_forbids_improper_tax_coupling`
([tests/test_ra_record.py:198](tests/test_ra_record.py#L198)) fails if the
e-invoicing tokens appear in `ra.py`. The exclusion survived the 15 August
inversion untouched, which is what §4.9 means by per-assertion.

### 4.9 What this does *not* unlock

**Inverting the assertion does not permit importing `quotation._tax_lines()`.**
That prohibition stands on its own reasons and survives unchanged:

- It is **document-total arithmetic** branching on a `tax_type` string it is
  handed ([quotation.py:79-98](quotation.py#L79-L98)). **It does not decide
  which tax head applies** — and §4.3 is precisely a rule about deciding that.
- It has **no per-line concept whatsoever**, and §4.4 is a per-line requirement.
- It lives in `quotation.py`, which is **forbidden to edit**
  ([INTRODUCTION.md](INTRODUCTION.md) §7). A dependency there is one that cannot
  be maintained.

`ra.py` grows its own. Likewise, e-invoicing tokens stay asserted-absent per
§4.8. **The inversion is per-assertion, not wholesale** — one test becomes
several, and some of its current absences remain.

**STATUS — held, and enforced.** `ra.py` grew its own tax block
(`_declared_rate`, `_head_split`, `tax_slabs`, `compute_tax_totals` —
[ra.py:1002-1220](ra.py#L1002-L1220)) and imports no `_tax_lines`; the
prohibition is pinned by `test_ra_forbids_improper_tax_coupling`
([tests/test_ra_record.py:198](tests/test_ra_record.py#L198)), which survived
the inversion. `ra.py`'s own import comment was corrected on 15 August 2026 to
state the three reasons above rather than the dead premise —
[STATE.md](STATE.md) §2.1's cleanup checklist records that it had been ticked
before it was true.

---

## 5. Documents their business uses that this system does not have

Recorded because they are real and shape future design. **Not scoped, not
queued** — see [STATE.md](STATE.md) for status. Do not build these.

### 5.1 Delivery challan

A document accompanying goods in transit. **Quantity and unit only — no rates,
no amounts.** The consignee is **Samruddhi's own site**, because they are moving
their own material to their own store on a project, not selling it to anyone.

It has no equivalent in this system.

### 5.2 Their purchase orders

The client's real POs differ from what `purchase.py` models:

- **They carry no GST.**
- They use **one running number series across all suppliers and all sites** —
  not a series per supplier and not a series per project.
- One variant carries a **`Pcs` column alongside `Qty`** — pieces as well as a
  measured quantity.

Combined with §1's multiple concurrent sites, this is the evidence that **site
is a first-class field** rather than a label.

---

## 6. THE PRINCIPLE — their data is imperfect, and it must survive

**The client's own data contains real defects. This system's job is to surface
them, never to repair them.**

Observed in their actual documents:

| Defect | What it is |
|---|---|
| **A duplicated item number** | Section A carries item `17` twice, on two different products with rates ~8× apart (§2.2). In their source workbook. |
| **Raw Excel date serials** | Dates stored as the underlying integer — `45874` rather than a date. |
| **The wrong state's GSTIN** | At least one supplier sheet carries a GSTIN belonging to a different state than the party it names. |

**Every guard in this system blocks, warns or flags. It never silently
corrects.** That is the whole design stance:

- The duplicate item 17 is **seeded exactly as it appears in their sheet**. The
  BOQ form shows a **non-blocking amber band** flagging repeated item numbers,
  which states on its face that billing is unaffected — because it is, since
  matching is on `line_id` (§2.2).
- An over-claim is **blocked**, with the reason named
  ([ra.py:581](ra.py#L581)) — not clamped to the approved quantity.
- A rate diverging from the approved BOQ rate **warns** and is stored as entered
  (§3.6) — not overwritten with the "correct" one.
- A missing base rate prints as `-` (§2.5) — not as zero.
- An uncertified line reports as uncertified (§3.5) — not as zero.

> **An agent trying to be helpful by cleaning up the client's data is the
> specific failure mode this document set exists to prevent.**
>
> Every one of those defects is somebody's real commercial record. A duplicate
> item number that gets deduplicated destroys a line worth ₹14,572.50 per unit.
> A date serial that gets "parsed sensibly" may land in the wrong year. A GSTIN
> that gets corrected to the state you inferred is a statutory identifier you
> just invented.
>
> If you find bad data: **surface it, name it, and stop.** Report what you
> found and what you propose. Do not fix it in passing, do not fix it as a side
> effect of another change, and do not fix it because it is obviously wrong. It
> being obviously wrong is not the question. Whose record it is, is.

The same stance governs the acceptance tests. They use the client's **real**
over-claim figures (§3.4) and the two rupee constants in §2.2. **Do not adjust
those numbers to make a test pass.** If a test carrying them fails, the code
changed — that is the test doing its job.

---

Next: [STATE.md](STATE.md) — where the work has got to, and what is next.
