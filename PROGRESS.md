# PROGRESS.md — Phase 3 build status

Regenerated from code, not from documentation. Every status below was
established by reading `.py` files and `tests/`; no status was taken from
ABOUT.md, STATE.md, DOMAIN.md or PHASE4_RA_DESIGN.md. Where a document and the
code disagree, the code won and the disagreement is recorded in §6.

Audience is the developer. Nothing here is client-facing and nothing here is
softened.

---

## 1. Header

| | |
|---|---|
| **Date** | 3 September 2026, **THIRTEENTH pass** *(a pass that moved **no bar at all**, and that is the honest headline. Three items, all authorised by a single new `CLIENT_CHANGES.md` §0 block — the **first of 3 September 2026** and the **twenty-first occasion overall** — and **not one of them is a CC-2 item**: the single-leg `tax_invoice_ref` is **DOMAIN.md §4.2's** requirement and goes to §4c as row 27, while the attachments half of the backup and `claimed_by_line()`'s merged walk are **defect fixes against work delivered on 2 September** and are §0's standing exemption. 3B stays at 8 of 8 and 3C stays at 5 of 6. ⚠ **C6 is STILL BLOCKED on Open question 4 and nothing here touches it.**)* |
| **Machine** | home laptop — `c:\Users\manas\OneDrive\Desktop\Demo_Works` |
| **Branch** | `antigravity-dev` |
| **HEAD** | `304cef2` — *"Phase 3: claimed_by_line() walks merged_ras…"*, the fifth of the five commits of this pass: the §0 block alone (`392a430`), the `.gitignore` entry (`9cd8a9c`), then Phase 1 (`d6ccc0f`), Phase 2 (`8bab9b1`) and Phase 3. This edition is written **after** them and describes the code as they leave it; it is itself the sixth. |
| **vs `origin/antigravity-dev`** | **75 ahead, 0 behind, unpushed** — measured with `git rev-list --left-right --count`, not assumed, and measured **before this edition was itself committed**, which adds one more. The pass began at **70 ahead, 0 behind**, one more than the previous edition predicted because that edition was itself committed after writing the figure. ⚠ **`main` is separately 21 ahead of `origin/main`** and this pass did not touch it. **Nothing has been pushed in a long while and that is not this pass's to decide.** |
| **Dirty files** | **0 — and the one that has blocked the gate for three passes is resolved.** `git status --porcelain` was **not empty** at the start of this pass: `?? 31AUG.md`, the same untracked 36-byte scratch note (*"# Changes / Updated Measurement Sheet"*) the twelfth pass found, took a judgement call on, and recorded. ⚠ **This pass STOPPED on the gate and asked**, which is what the brief required of it, and the owner chose to **gitignore the class** rather than commit or delete the file. `.gitignore` now carries `[0-9][A-Z][A-Z][A-Z].md` and its two-digit sibling, checked against every tracked `*.md` and catching none of them; the file itself is untouched on disk. ⚠ **NO LIVE RECORD WAS MUTATED BY THIS PASS.** One `mysqldump` was taken before any work — `backups/samruddhi_qms-20260903-224226-pre-3sep-ra-overage.sql` (**685,034 bytes**) — and **no migration, backfill or cleanup was run at all.** The live database was **read** in this pass, repeatedly and deliberately, and written **never**. |
| **Test figure** | **measured at the end of the pass: 2,034 passed, 2 skipped.** Configuration: global `C:\Program Files\Python310` (CPython 3.10.11), **no `.venv`**, openpyxl **absent**, both client workbooks **absent**. The baseline it moved from was **2,000 passed / 2 skipped**, re-measured in that configuration at the start of this pass rather than quoted — it matched the previous edition exactly. <br><br>The `.venv` configuration (CPython 3.10.11, **openpyxl 3.1.5 present**, workbooks absent) reports **2,035 passed, 4 skipped** against this commit and **2,001 / 4** at the start of the pass — both measured, neither derived, and both matched the previous edition exactly. The third configuration (*openpyxl present, workbooks present*) is still unmeasured; neither client workbook is on this box. <br><br>**+34 passed and +0 skipped in both configurations, reconciling exactly** and **measured per file rather than attributed**: two new files — `tests/test_backup_attachments.py` (**13**) and `tests/test_ra_tax_invoice_ref.py` (**18**) — plus **+3** in `tests/test_merged_ra.py` (33→36, the cancelled-merge release, the unrecognised-status direction and the foreign-project scoping). 13+18+3 = 34. <br><br>⚠ **NO GOLDEN MOVED.** All eleven assertions in `tests/test_print_golden.py` pass unchanged, as do `test_nav_reachability.py` and `test_page_chrome.py`. **The printed RA sheet's Tax Invoice No. line is the one thing that could have moved a golden and did not** — the goldens are built by `make_bill()`, which writes `tax_invoice_ref: ""` directly and never posts `/ra/create`, so a golden bill still takes the legacy `ref` fallback and prints exactly what it printed before. That is the grandfathered set behaving as specified, observed in the goldens rather than argued. <br><br>⚠ **`docs/ACCESS_MATRIX.md` DID NOT MOVE, and was regenerated rather than assumed** — `python tools/dump_access_matrix.py` produces a byte-identical file. **7 roles · 79 permissions · 127 classified endpoints**, all three unchanged: **no route was added and no permission was minted by any of the three items**, so no role needed a grant. `tools/reconcile_role_permissions.py` was run anyway and reported **nothing to do** — no orphan permissions, no drift. <br><br>⚠ **Two existing tests were rewritten and NEITHER was weakened or deleted**, each keeping its old assertions **verbatim** in the docstring: `test_a_single_leg_bills_tax_invoice_ref_is_UNCHANGED` (its premise is now the opposite of the rule, so it holds the invariant that survives — that merging writes no serial onto either leg — against values a bug could actually clobber) and `test_merging_does_not_move_the_overclaim_guard` (**its original assertion is unchanged and still runs**; what was added is the in-test mutation it was previously unable to catch). <br><br>⚠ **Every new guard is mutation-proved, and the proofs were RUN rather than asserted. Fifteen mutations, fifteen failures**: three on the backup archive (absolute paths, the dropped zip-slip check, a hardcoded store root), eight on the serial (reverting the mint, reading `ref` instead of `tax_invoice_ref`, len+1, series `RI`→`TI`, cap 16→64, `edit_ra()` backfilling a blank, `print_ra()` minting, a typed value overwritten) and four on the merged walk (reverting it, a cancelled document still counting, an unknown status reading as cancelled, dropping the chain scoping). <br><br>⚠ **THE 2 SEPTEMBER MUTATION THAT WAS *NOT* CAUGHT IS NOW CAUGHT BY THE RIGHT TEST.** The twelfth pass recorded that copying claim rows onto a merged record did not fail `test_merging_does_not_move_the_overclaim_guard`, and that the **shape** test beside it caught the defect instead. `ra.claimed_by_line()` now walks `merged_ras`, and the proof is stated as a **relationship**: reverting the walk fails that test **while the neighbouring shape test goes on passing**. That is what "caught by the function CC-2's warning is about" means, measured. <br><br>⚠ **THREE OF THIS PASS'S OWN NEW TESTS WERE VACUOUS WHEN WRITTEN, AND ONLY THE MUTATIONS FOUND THEM.** (1) The archive-path test asserted merely that no member was absolute, carried a drive letter or held a backslash — and `zipfile.write()` with no `arcname` **already** strips the drive, so it passed against exactly the unrestorable archive it forbade. (2) The Rule 46(b) cap test could not see the cap at all: `SF/RI/26-27/0001` is 16 characters whatever `_TAXREF_CAP` says, so raising it to 64 changed nothing observable. (3) **Both** `tax_invoice_ref` edit tests asserted only a `302` — which is also what a **refusal** returns — and the edit was in fact being refused, because `make_bill()` marks a bill **approved** by default and B7 locks an approved bill's figures. All four are fixed and re-proved. **A guard nobody has tried to break is a guard nobody has tested**, and that now applies to this pass's own work as loudly as to anybody else's. |

**Item source.** `CLIENT_CHANGES-2.md` only. Count found: **3A ×6 (A1–A6),
3B ×8 (B1–B8), 3C ×6 (C1–C6) = 20.** Matches expectation.

---

## 2. Bars

Only BUILT fills the bar. PARTIAL contributes nothing; BLOCKED contributes
nothing.

```
ALL  ███████████████████░  19 of 20 BUILT · 0 PARTIAL · 1 BLOCKED ·  0 NOT STARTED
3A   ████████████████████   6 of 6 BUILT · 0 PARTIAL · 0 BLOCKED ·  0 NOT STARTED
3B   ████████████████████   8 of 8 BUILT · 0 PARTIAL · 0 BLOCKED ·  0 NOT STARTED
3C   ████████████████▋░░░   5 of 6 BUILT · 0 PARTIAL · 1 BLOCKED ·  0 NOT STARTED
```

⚠ **The extra purchase-order lines are NOT on these bars, and must never be put
on them.** They are not one of CC-2's twenty items — no 3A/3B/3C tag, priced in
neither quotation, requested *after* the 19 August 2026 meeting that produced
the list. §4a carries them, outside the count, and **the defect fix this pass
made to them is outside it too**: cutting 156 invented aliases out of
`po_parts.py` repairs untagged work and does not become tagged by being
repaired. **The denominator is still 20.**

⚠ **THIS SECTION'S PROSE WAS TWO PASSES STALE AND IS REWRITTEN, NOT PATCHED.**
The fourth 29 August pass moved the bars 13 → 15 and the header with them, and
left every paragraph below saying what it said before — the same defect
`tests/test_doc_figures.py` was written to close for the **test figure**, one
field over, on a field that test does not cover. The stale sentence was *"The
board moved 12 → 13, and 3C moved 1/6 → 2/6"*, and it is recorded here rather
than deleted, because a board narrative nobody rewrites is a board narrative
nobody reads.

⚠ **THE BARS DID NOT MOVE THIS PASS, AND THAT IS THE POINT OF IT.** The eighth
pass of 30 August 2026 **corrected two delivered items rather than delivering a
new one**: C4's rate is a day rate and not a monthly salary, and C4/C5's `site`
comes from the address book and not from free text. Both were **our** misreading
of CC-2 rather than a change of mind by the client — CC-2's own note calls
`salary ÷ 8 × hours` *"1× ordinary rate"*, which settles the unit — and both
**mutated live records**. ⚠ **A correction is not a bar.** C4 and C5 were BUILT
and stay BUILT; the board stays at **17 of 20**, 3C stays at **4/6**, and the
denominator stays **20**. Anybody reading a moved bar out of this pass has read
it wrong. The same pass restyled the two register screens the owner has actually
opened, which is a §0 reachability item and on no bar at all.

⚠ **The NINTH pass of 30 August 2026 built NO CC-2 ITEM AT ALL, and this is the
easiest bar to move by accident.** It linked a project to the address book and
gave the address book integrity guards. **Neither is in CC-2**: there is no item
for a project→address join and none for the address book. The join sits
*adjacent to* **C6**, which is **BLOCKED** on Open question 4 and is **not
unblocked by it** — see §5. Both went into **§4c** as work beyond CC-2's text,
rows 16–18. **The board stays at 17 of 20, 3C stays at 4/6, and the denominator
stays 20.**

⚠ **NOR DID THE ELEVENTH PASS, AND IT IS THE HARDEST ONE YET TO READ CORRECTLY.**
It put a **`project_id` on an attendance marking** and split the Site Labour
section into *booked* and *unattributed* groups. That is a **project key on C5's
records and a project-level reading of them**, which looks more like C6 than
anything in this register — and it is not C6. **C6 is *"planned margin from the
BOQ against actual cost from purchase orders and recorded charges, with the
difference shown"*, blocked on whether attendance wages or the installation base
rate is authoritative.** This pass shows **no difference, no margin, no project
total, no net, and no authority**; it records which project a day was worked
for, which is a fact somebody on site knows, and it leaves Open question 4
exactly as open as it found it. §4c rows 22–24. **The board stays at 17 of 20,
3C stays at 4/6, and the denominator stays 20.** ⚠ **Four passes running have
now added to §4c without moving a bar**, and that is the register working rather
than the board being stuck.

⚠ **Every BUILT item was named by an override block, one at a time.** The
26 August 2026 OVERRIDE block in `CLIENT_CHANGES.md` §0 names the five 3B
items; the **27 August 2026** block names A1, A2 and A5 and explicitly refuses
A3; the **28 August 2026** block names A1's widening, A3 and A6; the first
**29 August 2026** block names **C4** and the untagged extra-lines work; the
**third 29 August 2026** block names **C5**, the navigation re-baseline and the
`po_parts.py` alias cutback; the **fourth** names **B6 and B7**; the **fifth**
names **C2 and C1**, the B7 narrowing, and two things carried forward from the
fourth; the **second 30 August 2026** block **AUTHORISES B8 and did not build
it**, and the **third** corrects C4 and C5 and authorises the two register
screens. Everything remaining — **B8**, authorised and unbuilt, and the two
BLOCKED items **C3** and **C6** — is NOT STARTED *and still gated*. A filled bar is not permission to
fill the next one.

✅ **3A IS CLOSED.** The three items that were not BUILT on 27 August each
turned out to be held by a **question**, not by code: A1 by a commercial one
(does A1-as-sold cover an issued order?), A3 by a tax one (is a charge inside
the taxable value?), A6 by a commercial one (should mid-chain editing be
allowed?). All three were put and answered on 28 August. Nobody wrote a line to
unblock them; somebody answered three questions, which is exactly what the
27 August edition predicted would be needed.

⚠ **A6 is BUILT WITH A STATED LIMITATION, which is not the same as BUILT.** The
latest-bill-only restriction was ruled **correct and kept**. A6 is BUILT because
the item as sold is delivered and the limitation is recorded in language the
client can be read; it is **not** a claim that arbitrary-bill editing works.
That is new scope and is priced nowhere. §6-A carries the wording.

📌 **Everything in this section that is ours rather than CC-2's is now listed in
one place: [§4c](#4c-built-beyond-cc-2--the-register).** The individual notes
below are kept exactly as their passes wrote them — this is a pointer, not a
replacement. §4c exists because a fact scattered across five override blocks is
a fact nobody can total, and the question *"what did we build that nobody
specified?"* deserves a single answer.

⚠ **B7 is BUILT, and a subsystem sitting beside it is OURS, unspecced and
unpriced.** CC-2's B7 governs **printing and downloading only**. It says nothing
whatever about editing. `approval.can_modify()` — an approved document is
locked, a part-climbed ladder is locked, a rejected one goes back to its creator
alone, an unstarted one is its creator's — was invented by the fourth 29 August
pass to fill that silence. Building it was right; an approval a later edit can
walk underneath is not an approval. **It is not B7, it is not delivered CC-2
scope, and nobody may cite it as either.** The fifth override block records it.

⚠ **B7's print gate was NARROWED the same day, by two named exceptions.** A
**draft** RA bill prints, carrying its DRAFT overprint, and a **cancelled** one
prints. The overprint is itself the safeguard B7 wants, and a cancelled bill is
the audit record of a withdrawn claim rather than a claim. What B7 reduces to on
an RA bill is now exactly *"an **issued** bill prints only once it is
approved"*. No other unapproved state moved, and the exemption is data on one
document rather than a rule in `can_print()` — a status test in the function
would have leaked to every unapproved draft purchase order.

✅ **3C IS OPEN, and C2 and C1 are the third and fourth items on it to move.**
The previous edition said C2 was *"NOT nearer than it was"* because it needed
an approval concept B6 had not yet supplied. B6 landed, which made C2
**possible**; what made it **authorised** was an override block naming it. The
distinction is the whole of why that note was written and it held.

⚠ **C2 IS BUILT AND MOST OF IT IS OURS.** CC-2's C2 is three lines — *"Raised
from the BOQ. Approved measurements become the source of installation quantity
on RA-Installation."* Two facts, and no more. The ceiling on a measured
quantity, that the ceiling is cumulative across sheets, **which ladder** a
measurement climbs, and that the sheet **prints at all** are every one of them
**ours, unspecced and unpriced**. They are named individually in the fifth
29 August override block. A measurement document without them is a form that
records a number nobody checks — and that does not make them delivered C2.

⚠ **C1 IS BUILT, and the supply leg did not exist before it.** Nothing outside
`challan.py` read `STORE["delivery_challans"]` — not `ra.py`, not the BOQ page.
`BoQ → Delivery Challan → RA-Supply` was two unconnected documents. **Refusing
by URL rather than by hiding a button is ours**: C1 states a domain model and no
mechanism, and B5's rule supplied the mechanism. The two legs are deliberately
asymmetrical — installation gets an ordering guard **and** a quantity ceiling,
supply gets the ordering guard alone, because CC-2 puts no quantity on the
challan arrow and `challan.BLOCK_OVER_DISPATCH` is False on purpose.

⚠ **ONE live RA bill was grandfathered, and the set is closed.** Seven RA bills
exist, one is on the installation leg, and it carries a typed quantity with no
measurement behind it: `SF/RA/26-27/0006`, RA1 on project *Work2*. It keeps its
figures, renders a "Typed quantity" marker **on screen only**, and
`tests/test_measurement_pin.py` fails if an installation bill created after the
pinned moment joins it. **That test is the point of the rule**, and a second
test plants exactly such a bill to prove the sweep can see one.

⚠ **C5 is BUILT and is NOT wired into C6**, and C2 did not change that. It
consumes the employee master and produces a site-wise labour cost displayed
inside its own module and nowhere else, held by an AST test asserting no module
imports it. **C6 stays BLOCKED** on CC-2's Open question 4: attendance-based
wages and the BOQ's installation base rate both represent labour, and
subtracting both counts it twice.

⚠ **The OT multiplier is a SETTING and no literal multiplier is in the
calculation code**, which is CC-2's own requirement. The client's figure is 1×
ordinary rate; statutory overtime is generally twice; hardcoding the first would
make this software compute an **underpayment**. Held by a behavioural test and
by an **AST walk** that fails on a numeric constant in a multiplication or a
division inside `daily_wage()`, `ot_amount()` or `cost_of()`.

**The board moved 15 → 17**, and 3C moved 2/6 → 4/6. Two items moved, and they
are the two the fifth 29 August override block names. ~~**After this, B8 is the
only buildable item left**~~ — C3 is blocked on BQ1 and BQ2, C6 on Open question 4
— and that is emphatically not an authorisation to build it.

⚠ **The struck clause was falsified on 30 August 2026, and by the pass sent to
act on it.** B8 was **authorised** that day (second 30 August override block)
and then **could not be built**: `db.py` persists by snapshot-and-diff and
cannot carry a binary side table, measured three ways in ABOUT.md §4. So B8 was
not "the only buildable item left" — it was the only *authorisable* one, and
buildability is a separate question that nobody had asked of it. **The board
stands at 17 of 20 and no item is buildable today**: C3 and C6 wait on the
owner and the client, and B8 waits on a storage decision the owner has to
take.

---

## 3. What the bars do not say

**The item count does not measure the work.** These twenty items are not
comparable units and the ratio 17/20 is close to meaningless as a measure of
effort remaining. A2 is a column on one form. B5 was a decision applied to every
route in the application, and B8 — the one item left — breaks the storage model
this whole application rests on. **That last clause was written as a prediction
and has now been measured true**: the 30 August pass sent to build B8 stopped on
it without writing a line of attachment code.

**B5 is now built, and it cost less than this section predicted.** The 25 August
edition called it "a decorator on every route function in every module" and the
largest single item in Phase 3. It was built instead as **one central
registry and one `before_request` hook** — `auth.py` is a new file and `app.py`
gained one line; no route function in any other module was touched. The
prediction was wrong about the shape, and the reason is worth keeping: a
decorator scheme fails **open** when somebody forgets one, and default-deny only
works by *absence*, which a decorator cannot express. What the registry costs
instead is a second thing to keep in step with the routes, and
`test_every_endpoint_is_classified` is what pays for it.

~~**3A is now the smallest thing left, and none of it is engineering.**~~
**3A is closed, and the prediction it carried was right.** The 27 August edition
said of the three items still open that *"nobody has to write code to unblock
any of the three; somebody has to answer three questions."* The three questions
were put on 28 August and answered — A1's Draft-only narrowing (commercial), A3's
tax base (statutory), A6's latest-bill-only restriction (commercial) — and all
three items closed in one pass. Two of the answers were *build it*; the third,
A6's, was *the restriction is correct, keep it*, which is why A6 closes as
**built with a stated limitation** rather than by having code written for it.

**Worth keeping about how that went.** The item that cost the previous pass a
day was the one where the code could not tell you the answer: A3 was stopped
because a charge line on a buy-side PO is inside or outside the GST base
depending on **who performs the work**, and there was no existing code path to
read that off. Stopping was right. What unblocked it was noticing that the
document itself settles it — a purchase order is issued **to a named vendor**, so
a line on it is that vendor's consideration by construction, and the third-party
reading describes a cost that would appear on a different document altogether.

Two items now dominate what is left of Phase 3:

- **B8 — file attachments.** The first thing that breaks the storage model.
  There is no `/static`, images are base64 data URIs, and `boq.MAX_JSON_BYTES`
  is 300,000 ([boq.py:192](boq.py#L192)) against a photographed supplier bill
  of 2–5 MB. This is new infrastructure — a real file store, a path on the
  record, a size and type gate, and cascade delete — not a field.
  ⚠ **AUTHORISED 30 August 2026 and still NOT STARTED**, which is a state no
  other item has been in. The blocker is no longer commercial: it is that
  `db.py` cannot carry the payload (ABOUT.md §4), and the fix is a persistence
  decision the owner has to take, not one an agent may take for him.
- **C3 — merged RA.** Blocked before it starts (§5), and the design pass that
  unblocks it has to settle a statutory numbering question the repo currently
  answers both ways.

~~B1/B2/B3/B4 are individually smaller but strictly sequential and strictly
prior: none of 3C can be built until a user exists.~~ **Done — a user now
exists, and 3C is no longer blocked on identity.** It is still gated: the
26 August override covers B1–B5 and nothing else.

**What B6 needs that this pass did not give it.** The gate is **endpoint-level**
(ABOUT.md §7 gap 24). B6's load-bearing rule — *a user cannot approve a record
they created, checked against the record's creator* — is not expressible in
`ROUTE_PERMISSIONS` and must be a per-view guard against `created_by`. Nothing
in this pass makes that check easier; it only makes it possible, by giving
records somebody to have been created by.

---

## 4. Items

### 3A — document and register changes

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **A1** | PO base rate editable | **BUILT** | **Both halves now exist.** At creation: `RATE_PREFILL_FIELD = "supply_base_rate"` [purchase.py:182](purchase.py#L182), rate box on `GET,POST /purchase/from-boq/<boq_id>` and `GET,POST /purchase/from-draft/<draft_id>`, test `test_rates_prefill_from_the_supply_base_rate_and_an_edit_is_what_is_stored` [tests/test_boq_to_po.py:240](tests/test_boq_to_po.py#L240). **On an existing order (new, 27 Aug 2026):** `GET,POST /purchase/edit/<id>` → `purchase.edit_purchase_rates()`, gated by `can_edit_rates()`, arithmetic in `_reprice()`; [tests/test_po_rate_edit.py](tests/test_po_rate_edit.py). Classified `purchase.create` in `auth.ROUTE_PERMISSIONS`. **The Draft-only narrowing was LIFTED on 28 Aug 2026** — `can_edit_rates()` now refuses **only** `Cancelled`, and every reprice that moves a figure writes a `reprice_log` entry (who, when, old rate → new rate, per line that moved) rendered under the order by `_reprice_html()`. **32 tests in that file** (21 before this pass), of which 4 were the narrowing's own and are rewritten with their old assertions kept verbatim in comments. | Nothing for A1. **§6-I is CLOSED.** The narrowing that held this row at PARTIAL is gone and the objection it protected is answered by the record rather than by the refusal — see §6-I. Still deliberately not editable there: quantities, lines, the vendor and the tax **type**, which is a fact about where the vendor is rather than a price. A **Cancelled** order is refused, which is a rule about a void document and not a lifecycle narrowing. | ☐ |
| **A2** | Discount column on final PO | **BUILT** | Per-line discount **percentage**, inside the tax base. `MAX_DISCOUNT_PCT`, `_parse_discount()` and `_line_total()` in [purchase.py](purchase.py); `DS.BUY_COLUMNS` and the `blanks` parameter on `DS.sum_row()` / `DS.total_row()` in [docsheet.py](docsheet.py); `.c-disc` in `PURCHASE_STYLES`; rendered by `view_purchase()`. 22 tests in [tests/test_po_discount.py](tests/test_po_discount.py), of which `test_the_discount_reduces_the_tax_because_it_is_inside_the_tax_base` is the load-bearing one. Golden re-baselined **+942 bytes**, justified field by field. | Nothing for A2. The discount is settable at `/purchase/create` and, for a BOQ-derived order, at `/purchase/edit/<id>` — `_po_lines_from_picked()` writes no `discount_pct`, by design. | ☐ |
| **A3** | Additional charge lines on final PO | **BUILT** | **One repeater, `PO_CHARGE_SLOTS = 4` free-text slots**, on `/purchase/create` and `/purchase/edit/<id>`. `_parse_charges()`, `charges_of()`, `charge_totals()` and the `charges` parameter on `_totals_of()` in [purchase.py](purchase.py); `.chg-*` in `PURCHASE_STYLES`; printed as `DS.sum_row()` rows by `view_purchase()`. Stored as `{"label", "amount", "taxable"}` beside a new `taxable_value` on the record. 25 tests in [tests/test_po_charges.py](tests/test_po_charges.py), of which `test_the_worked_example_from_the_report` is the load-bearing one. Golden re-baselined **+937 bytes**, all of it stylesheet. | **§6-H is CLOSED — the tax question was answered, not worked around.** The charge is **inside** the taxable value: a line on a PO we issue to a named vendor is consideration for that vendor's supply, s.15(2)(c). The exception is expressible anyway — every line carries `taxable`, defaulting to true, and an untaxed line is added **after** tax. ⚠ **One part of CC-2's A3 note is NOT built and is a recorded deviation:** the heads are not seeded in `/settings` and not editable there. Reading them would add a `purchase.py → settings.py` import edge for labels that are already free text. Named in the 28 Aug override block for the client-facing owner to confirm. Also deliberate: no repeater on `/purchase/from-boq` or `/purchase/from-draft`. | ☐ |
| **A4** | Total outstanding on client register | **BUILT** | Computed in `client._client_groups()` from `issued_val` less `received_val` **less `written_off_val`** (new, 27 Aug); rendered on `GET /client/`. Original tests `test_outstanding_counts_issued_bills_only` and `test_receipts_reduce_outstanding_and_an_overpayment_shows_as_credit` [tests/test_client_segregation.py](tests/test_client_segregation.py) untouched; +10 verification tests in [tests/test_client_outstanding.py](tests/test_client_outstanding.py). | Nothing for A4 itself, and **§6-D is now closed on its presentational half**: `OUTSTANDING_CAVEAT` states under the figures that Outstanding is internal and that no credit note stands behind a write-off, which is what CC-2's A4 note asks for in as many words. The **arithmetic** half of §6-D is still open — see A5's row and §6-D. | ☐ |
| **A5** | Write-off / adjustment on a payment | **BUILT** | A `write_off` amount on the receipt record, written by `receipt.new_receipt()` and `receipt.edit_receipt()`, validated in `receipt._validate()`, summed by `ra.written_off_against()` and subtracted in `ra.outstanding_of()`. Visible on the receipts ledger, the bill's receipts panel, the form's facts block and the client register. 21 tests in [tests/test_receipt_write_off.py](tests/test_receipt_write_off.py). | Nothing for A5 as CC-2 specifies it. **Two things worth knowing rather than left silent:** it is a field *on a payment*, so a standalone write-off against a bill with no payment at all is not expressible — CC-2 words A5 that way and this follows it. And it is **not** a credit note: no document, no number series, stated on the form itself. | ☐ |
| **A6** | RA edit and delete — draft only | **BUILT** *(with a stated limitation)* | **Not one line of `ra.py`'s lifecycle logic was touched on 27 or 28 August.** All three routes exist and are gated: `GET,POST /ra/cancel/<id>` by `can_cancel()`, `GET,POST /ra/edit/<id>` by `can_edit()`, `GET,POST /ra/delete/<id>` by `can_delete()`. **Verified end to end on 28 Aug 2026**, driven through `/ra/create` → `/ra/edit` → `/ra/print` and `/ra/delete` rather than against the gate functions: 11 tests in [tests/test_ra_edit_delete.py](tests/test_ra_edit_delete.py), covering the edit reaching the printed bill, the delete freeing the quantity it claimed, and the number being reused where a cancelled one stays spent. What **did** change is `frozen_reason()` and `can_delete()`'s frozen branch, which now explain why and name cancelling forward. | ⚠ **The latest-bill-only restriction STAYS, and that is the stated limitation — see §6-A.** It was put up as a candidate for lifting and was ruled **correct behaviour, not a shortfall**: RA bills are cumulative, so editing bill 3 while bill 5 exists corrupts every claim downstream of it. **Arbitrary-bill editing is NEW SCOPE** and is priced nowhere. Nobody may record the limitation as a defect owed to the client. | ☐ |

### 3B — users, access and approvals

⚠ **Nothing in this section changed build state on 27 August 2026** — across
three passes that day. The first escaped user text everywhere it reaches HTML
and **attacked** the layer B1–B5 shipped; the second added break-glass password
recovery and a second Owner; the third attacked `/users/*` as a Director and
**found a privilege escalation**. None of them built a Phase 3 item and none
started anything gated. B1–B5 stay BUILT, B6–B8 stay NOT STARTED and gated.
*(Superseded twice since: B6 and B7 were built on 29 August 2026, and B8 was
authorised — though not built — on 30 August 2026. Kept as it stood.)*
What changed is how much of B1–B5 is *verified* rather than asserted, and that
is recorded in the B1, B3, B5 and B6 rows below.

⚠ **A BUILT item can still be wrong.** B3 was marked BUILT on 26 August with
`_may_grant()` cited as the thing that holds it, and it did hold the door it was
written for. The escalation found on 27 August walked through a **different**
door on the same page — the password field — which no cell in this table had
ever claimed anything about. **Read a BUILT row as "this exists and these tests
hold it", never as "this was attacked".** [STATE.md §1.12](STATE.md) is the plain-English account;
[docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md) is the generated 7×79 grid, with
every cell marked specification-or-derivation.

**B1–B5 built 26 August 2026** in [auth.py](auth.py) (1,670 lines), under the
dated **26 August 2026 OVERRIDE** in `CLIENT_CHANGES.md` §0. The application is
now closed: `auth.enforce(app)` [app.py:158](app.py#L158) installs a single
`before_request` gate that refuses **any** of the **127** endpoints not classified in
`auth.ROUTE_PERMISSIONS` [auth.py:236](auth.py#L236).

The `SECRET_KEY` demo fallback recorded here on 25 August is **gone**:
`auth.resolve_secret_key()` [auth.py:70](auth.py#L70) reads
`SAMRUDDHI_SECRET_KEY`, then `SECRET_KEY`, then a gitignored `secret_key.txt`,
with no hardcoded fallback. ABOUT.md §7 gap 8 is closed.

~~**B6, B7 and B8 remain NOT STARTED and remain gated.**~~ **B6 and B7 were BUILT on 29 August 2026 (fourth pass) under the fourth override block of that date; B8 alone remains NOT STARTED and gated.** The struck sentence is kept rather than deleted because it stood through a pass that made it false — the same staleness §2 above records of itself.

⚠ **And the replacement sentence has itself gone half-stale, on 30 August 2026.** B8 is **no longer gated** — the second override block of that date authorises it. It is **still NOT STARTED**, for a reason that is now technical rather than commercial: see its row below and ABOUT.md §4. Recorded here rather than by editing the sentence above, for the reason that sentence itself gives.

⚠ **Two deliberate deviations from CLIENT_CHANGES-2.md**, both decided by the
client-facing owner before code was written and both recorded in the override
block: B5's two-stage audit-mode rollout was collapsed into immediate
enforcement (with the logging half kept as a condition), and B3's **Owner** tier
ships as a seventh role beside B4's six. Do not read either as spec drift.

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **B1** | user accounts and login | **BUILT** | `users` collection [store.py:44](store.py#L44), persisted via [db.py:75](db.py#L75). `GET,POST /login` `auth.login()` [auth.py:944](auth.py#L944); `GET,POST /logout` [auth.py:990](auth.py#L990) (GET confirms, POST destroys); `GET,POST /setup` [auth.py:1090](auth.py#L1090); `GET,POST /account` [auth.py:1025](auth.py#L1025). Hashing is `werkzeug.security` — `create_user()` [auth.py:508](auth.py#L508). `SECRET_KEY` moved: `resolve_secret_key()` [auth.py:70](auth.py#L70). Bootstrap also non-interactive: [tools/seed_users.py](tools/seed_users.py). Tests: `test_a_correct_password_signs_in`, `test_a_wrong_password_does_not`, `test_a_deactivated_user_cannot_sign_in`, `test_logout_needs_a_post`, `test_the_demo_secret_key_is_gone_from_the_codebase` [tests/test_auth.py](tests/test_auth.py). | Nothing for B1. ✅ **§7 gap 21 is closed (27 Aug 2026)** — it needed a decision, the decision was *both*, and the install had already walked into the failure it described: the seeded Owner's password was recorded nowhere. [tools/set_password.py](tools/set_password.py) is the break-glass CLI and a **second active Owner** is the operational half. **§7 gap 22 is still open** — no rate limiting on `/login`, still not a code fix until a decision is taken. <br><br>✅ **27 Aug 2026:** `/login`'s username-enumeration **timing** oracle is closed (§7 gap 25) — a real username took 70 ms to reject and an unknown one 0.3 ms, **239x**, because only the real one hashed. The not-found path now hashes against `_DUMMY_HASH`; measured 1.00x. Gap 22 is **narrowed, not closed**. | ☑ |
| **B2** | permissions are named strings, minted in code | **BUILT** | **79** permissions in `auth.PERMISSIONS` (61 when this row was written; the figure is measured off the catalogue each pass and this one had gone two passes stale) [auth.py:120](auth.py#L120), each with a label and display group, derived from `app.url_map`. Roles are editable data: `GET,POST /roles/edit/<id>` [auth.py:1562](auth.py#L1562) renders checkboxes over the catalogue. The client cannot mint a string — `_posted_permissions()` [auth.py:1514](auth.py#L1514) drops anything not a catalogue key. Effective permissions are the **union** of roles: `permissions_of()` [auth.py:540](auth.py#L540). Tests: `test_a_role_cannot_be_given_a_permission_that_does_not_exist`, `test_editing_a_role_takes_effect_without_signing_in_again`, `test_every_catalogue_permission_gates_something` [tests/test_access_control.py](tests/test_access_control.py). | Nothing for B2. **Deviation from CC-2's wording:** the assignment surface is `/roles`, not `/settings`. `/settings` is the company-identity form and mixing an access matrix into it would put a lockout one mis-click from a bank-details save. | ☑ |
| **B3** | Owner / Admin split | **BUILT** | Modelled as *"Owner is exactly whoever holds `admin.roles`"* — `is_owner()` [auth.py:557](auth.py#L557) — so there is no tier field to disagree with the permissions beside it. Only an Owner may grant an Owner role: `_may_grant()` [auth.py:1150](auth.py#L1150). The last active Owner cannot be deactivated **or edited out of the tier**: `_would_strand_install()` [auth.py:1169](auth.py#L1169). Role floors: `_role_edit_refusal()` [auth.py:1197](auth.py#L1197). Tests: `test_the_last_owner_cannot_be_deactivated`, `test_the_last_owner_cannot_edit_their_own_owner_role_away`, `test_an_admin_cannot_grant_themselves_the_owner_role`, `test_an_admin_can_still_create_an_ordinary_user`, `test_the_owner_role_cannot_lose_the_permission_that_defines_it`. | ✅ **27 Aug 2026:** the recovery hole is closed. *"More than one Owner is permitted and untested in anger; a single-Owner install has no recovery path if that password is lost"* — that was written the day before this install proved it, and it is no longer true of this install: **two active accounts hold `admin.roles`**, either can reset the other at `/users/edit/<id>`, and [tools/set_password.py](tools/set_password.py) is the path back in when neither can sign in. Both were driven through the real `/login` against live MySQL — 33 of 33 checks. ⚠ **Still open:** password reset is **undocumented for the client** — `/account` says only *"an Owner sets a new password for you"*. That is the half of §7 gap 21 this pass did not close, and it is a client-facing writing job, not code. <br><br>🔴 **27 Aug 2026, the day's third pass: the tier split had a hole in it, and it was the password field this row had just finished celebrating.** `/users/edit/<id>` sets a password for any account `admin.users` can load. A **Director-only** account set the **Owner's** password, changed no role, signed in as the Owner and reached `/roles` with a 200 — the one page B3 says they may never reach. Four more of the same shape got through: the Owner role taken **off** a spare Owner, an Owner deactivated, a dormant Owner reactivated, and a limited `admin.users` role conferring `charge.*` it does not hold. ✅ **Closed in the same pass.** `_may_grant()` [auth.py:1181](auth.py#L1181) now tests the **whole** permission set of every role assigned, not just `admin.roles`; `_may_administer()` [auth.py:1227](auth.py#L1227) is its mirror and refuses any change to an account holding a permission the actor lacks; `_administer_refusal()` [auth.py:1272](auth.py#L1272) renders and **logs** it. Guards `/users/edit`, `/users/deactivate`, `/users/activate`, GET and POST. 17 tests in [tests/test_privilege_escalation.py](tests/test_privilege_escalation.py), **7 failing against the pre-fix code**. §7 gap 26; [STATE.md §1.14](STATE.md). 📌 **Tightened past the letter of B3**: a Director can no longer administer an Owner account at all, which B3 does not ask for — the reasoning is in gap 26. | ☑ |
| **B4** | roles as discussed | **BUILT** | Seven builtin roles seeded idempotently by `ensure_builtin_roles()` [auth.py:469](auth.py#L469) from `BUILTIN_ROLES` [auth.py:392](auth.py#L392) — B4's six plus B3's Owner. Multi-role assignment is a checkbox list on `/users/create` and `/users/edit`; effective permissions are the union. HR restriction applied literally to `charge.*`, the wages ledger being the only employee data the app holds. Tests: `test_the_six_client_roles_and_the_owner_are_seeded`, `test_hr_information_is_kept_from_sales_purchase_and_accounts`, `test_permissions_are_the_union_of_several_roles`, `test_re_seeding_does_not_undo_an_owners_edit`. | ⚠ **The per-role permission sets are a derived starting position, not a client instruction.** CC-2 carries **no per-role grid** — B4 names the roles and states one restriction. Walk the seven roles through with the client. HR's real surface arrives with C4 (employee master); until then HR holds only the charge ledger. | ☑ |
| **B5** | default deny, rolled out in audit mode | **BUILT — with a recorded deviation** | Central registry `ROUTE_PERMISSIONS` [auth.py:236](auth.py#L236) classifying all **127** endpoints (72 when this row was written; 111 until the fourth pass of 30 August 2026 added the address book's view page and its two archive routes; **114 until 2 September 2026, when B8 added six and C3 added seven** — B8's three per attachment parent type under `charge.*` / `receipt.*`, and C3's five merged-document pages plus its two approval endpoints under `ra.*`; **all thirteen under permissions that already existed and NEITHER item minted one**); single hook `_gate()` [auth.py:669](auth.py#L669) installed by `enforce()` [auth.py:740](auth.py#L740) at [app.py:158](app.py#L158). **Absence refuses** — proved, not claimed, by `test_an_unregistered_endpoint_is_refused`. The sweep CC-2 asks for is `test_every_endpoint_is_classified`, over `app.url_map`; `test_no_non_public_endpoint_is_reachable_without_a_session` sweeps every endpoint anonymously. 13 tests in [tests/test_access_control.py](tests/test_access_control.py). | ⚠ **Audit mode was not run.** CC-2 asks for log-only then flip; this enforces from the start, by decision recorded in the override block. **The logging half was kept as the condition of that decision** — every refusal records user, endpoint, permission and reason to `REFUSAL_LOG` [auth.py:626](auth.py#L626) and `app.logger`, readable at `GET /access-log` [auth.py:1604](auth.py#L1604). Also: the registry is **endpoint-level only** — §7 gap 24, which B6 inherits. <br><br>✅ **27 Aug 2026, verified by attack rather than by its own tests.** Eleven adversarial probes in [tests/test_access_control_adversarial.py](tests/test_access_control_adversarial.py); **nine clean, two holes**. Forged/unsigned cookies refused, deactivation and role edits landing on the next request, all 7 roles correct on every admin URL by direct hit, every lockout guard refusing a direct POST, `/setup` refusing a POST, no error page rendering before the gate, a route added to the live `url_map` refused even to an Owner, and the refusal log carrying no credentials. The holes were the timing oracle (B1's cell) and **§7 gap 24b** — `POST /projects/view/<id>` wrote under the read permission `project.view`, because one endpoint carries one permission across both methods. Fixed with a per-view guard; a sweep now fails on any future rule that accepts POST under a `*.view` permission. <br><br>✅ **27 Aug 2026, third pass: the registry now also decides what is *shown*.** `can_reach(endpoint)` [auth.py:726](auth.py#L726) answers the gate's question from the same `ROUTE_PERMISSIONS` dict, and every nav entry and dashboard card is drawn only when it says yes — so a user is no longer offered fifteen doors, eleven of which refuse. **Derived, not listed:** `dashboard.py` names no permission id in code at all (asserted from its AST), and `test_can_reach_agrees_with_the_gate_on_every_endpoint_for_every_role` sweeps 7 roles × every classified GET endpoint comparing prediction with what the gate actually did. **Hiding did not replace anything:** every hidden card is hit by URL for every role and must still refuse, with a control requiring the visible ones to open. 49 tests in [tests/test_nav_visibility.py](tests/test_nav_visibility.py), 31 failing against the pre-pass code. [STATE.md §1.16](STATE.md); the figures on `/` are **not** filtered and that is [ABOUT.md §7 gap 27](ABOUT.md), open. | ☑ |
| **B6** | approvals | **BUILT** | New bottom-of-graph module [approval.py](approval.py), imported by the four approvable document modules and importing none of them. Both ladders read off CC-2 and **the difference between them kept**: charges are `("director", "operation-head", "hr")` with `sequential=True` — CC-2 writes *"in sequence"* — and RA / Tax Invoice / PO are `("operation-head", "director")` with `sequential=False`, because CC-2 writes *"Operations Head + Director"* with no ordering word. Any one Director's approval satisfies the Director rung. Eight endpoints (`approve_<key>` / `reject_<key>`) minted from `approval.DOCUMENTS` and classified individually in `auth.ROUTE_PERMISSIONS`; four permissions minted; `docs/ACCESS_MATRIX.md` regenerated and moved **only** in those four rows. **34 tests** across [tests/test_approval.py](tests/test_approval.py) (24) and [tests/test_approval_grandfather.py](tests/test_approval_grandfather.py) (10). <br><br>⚠ **THE CREATOR GUARD IS WHY THE MODULE EXISTS.** This document's previous edition recorded that `ROUTE_PERMISSIONS` cannot carry a per-record condition, and B6's load-bearing rule is exactly one. So it is a per-view check, written **once** in `can_approve()`, and an AST test asserts every approval view reaches it. It is checked against the **record's creator**, never the approver's role — CC-2's own reason being that union permissions defeat the ladder, and a role test cannot see a union. CC-2's worked example (*"a user holding both Sales Manager and HR"*) is built and asserted. <br><br>⚠ **`created_by` MUTATED LIVE RECORDS.** `tools/backfill_created_by.py` ran against the live database and marked **15 records** — **5 charges, 7 RA bills, 1 tax invoice, 2 purchase orders** — as predating the approval system, pinned at `2026-08-29 19:55` in `STORE["settings"]["approval_migration"]`. Grandfathered records **are** approvable, because the creator guard cannot apply where there is no creator, and they say so on screen and never on paper. **The pin is the deliverable, not the backfill**: `test_approval_grandfather.py` fails if any record created after that moment lacks a creator or carries the mark. | Nothing of B6 as CC-2 words it. **Three things to know rather than discover, all OURS and all flagged:** ⚠ **One user may not climb two rungs of the same ladder.** CC-2 does not say it; B4 lets one user hold several roles, so without it a Director-and-HR user climbs two thirds of the charges ladder alone — CC-2's own "union permissions defeat the ladder" failure by another route. ⚠ **The Owner satisfies any rung** (B3: "Everything") and stays bound by the creator guard and the one-rung rule, which is what keeps "Everything" from meaning "alone". ⚠ **The RA / Tax Invoice / PO pair is UNORDERED**, read off CC-2's omission of "in sequence". If the client wants it ordered it is a one-word change. | ☐ |
| **B7** | unapproved documents are view-only | **BUILT** | `approval.can_print()` gates `GET /ra/print/<id>` [ra.py](ra.py) and refuses **by URL** with the reason, not by hiding the Print button. `approval.print_block()` supplies B7's second bullet — a `@media print` stylesheet that blanks the page — and an **approved** document emits nothing at all, which is why **not one digest in [tests/test_print_golden.py](tests/test_print_golden.py) moved**: all 11 golden tests pass against baselines that were re-measured, not re-baselined. A grandfathered document prints, for the reason the whole grandfather rule exists. **30 tests** in [tests/test_approval_b7.py](tests/test_approval_b7.py) (24 before this pass). <br><br>⚠ **NARROWED 29 August 2026 (fifth pass) by TWO NAMED EXCEPTIONS, and by no others.** `approval.DOCUMENTS["ra"]["print_exempt_states"] = ("draft", "cancelled")` — a **draft** RA bill prints carrying its DRAFT overprint, and a **cancelled** one prints. What B7 reduces to on this document is now exactly *"an **issued** bill prints only once it is approved"*, which is the document B7 is about. Pending, part-climbed and rejected all still refuse by URL on an issued bill, and every unapproved document of the other four types still refuses whatever its own status field says. The exemption is **data on one document, not a rule in `can_print()`**: `purchase.PO_STATUSES` also carries "Draft" and "Cancelled", so a status test in the function would have silently exempted every unapproved draft purchase order. <br><br>⚠ **`/invoice/view/<id>` and `/purchase/view/<id>` HAVE NO SEPARATE PRINT ROUTE** — they render the A4 sheet itself. B7's first bullet assumes view and print are different URLs, which is true of the RA bill and false of these two; gating them would refuse the viewing B7 explicitly permits. **So B7's second bullet is the whole gate there** and the route stays open. That is a finding about this application's shape, not a choice. | ⚠ **B7 SAYS NOTHING ABOUT EDITING. `approval.can_modify()` IS OURS, UNSPECCED AND UNPRICED, AND IT IS NOT PART OF DELIVERED B7.** CC-2's B7 governs **printing and downloading only** — *"an unapproved document may be viewed, but not printed or downloaded"*, the print and download routes gated, and a print stylesheet so `Ctrl+P` does not walk round the gate. That is the whole of the item. **Nobody may cite `can_modify()` as a delivered CC-2 requirement or as work MG/SF/2026-02 covers.** The fifth 29 August override block records it by name, on the fifth pass's own disclosure. Building it was right — an approval a later edit can walk underneath is not an approval — and that does not make it specified. <br><br>⚠ **The rules themselves.** Who may edit before submission, whether an approved document may be changed, whether a rejected one returns to editable — CC-2 settles none of the three. Our rules, each the restrictive reading bar one: **approved is locked**; **part-climbed is locked**; **rejected returns to its creator only** — ⚠ the one place the restrictive option was *not* taken, because "no" strands the record: an issued RA bill that is rejected also cannot be deleted (`can_delete()` refuses an issued bill) and cannot be printed. <br><br>✅ ~~**TWO COLLISIONS WITH EXISTING DELIBERATE DESIGN, both carried as open questions.**~~ **BOTH ANSWERED on 29 August 2026 by the fifth override block, the same day they were raised** — and the history is kept rather than deleted, because the way it went is the point. The strict reading gated the printed **DRAFT working copy** and the **CANCELLED** record that morning; both were readmitted that evening. The reasoning: the DRAFT overprint *is* the safeguard B7 wants, so gating the print removed the safeguard's purpose along with it; and a cancelled bill is not a claim but the audit record of a withdrawn one, and a record that cannot be produced is not a record. A test asserts the overprint renders on **every** draft print — plain, pending **and rejected** — because a draft that printed clean would be worse than either reading. ⚠ **A rejected DRAFT prints, and that ordering is OURS**: lifecycle state and approval state are orthogonal, the exemption is checked before the rejected clause, and the block's wording admits both readings. <br><br>⚠ **`/purchase/<id>/update` is deliberately NOT gated** — it changes no figure, and locking a goods receipt behind an approval ladder would stop a storekeeper recording a delivery that has physically happened. | ☐ |
| **B8** | file attachments | **BUILT** | [attachment.py](attachment.py) (817 lines), 2 September 2026, under the **first override block of that date** — which is also the block that took the storage decision the row below had been waiting on since 30 August. **Files on disk, path on the record**, which is CC-2's own wording: the pass did not depart from the specification, it **returned** to it, and the 30 August BLOB choice was the departure. Store at `attachment.root()` — `<repo>/attachments/`, gitignored, overridable with `ATTACHMENT_DIR`, **served by no static route** because this app has none. `STORE["attachments"]` is an ordinary JSON collection in `db.COLLECTIONS` holding `filename`, a **relative** `stored_path`, `size_bytes`, the **sniffed** `mime_type`, `parent_type` + `parent_id`, `uploaded_by`, `uploaded_at` and a `sha256`. **Type by magic bytes** (`SIGNATURES`) — never the extension, never the browser's `Content-Type`. **5 MB cap** checked before anything reaches the store. **Compulsory on a charge at two doors** — `new_charge()` refuses without a file, and `_do_delete()` refuses to remove the last one. **Optional on a receipt.** **Cascade** from both parents deletes the **file and the row**. **38 tests** in [tests/test_attachments.py](tests/test_attachments.py). ABOUT.md §3 (Attachment) and §4. | ⚠ **Not enforced on an EDIT — the grandfather rule.** Every charge raised before 2 September 2026 has no attachment, and requiring one to fix a typo would mean finding a two-month-old paper bill first. Same reasoning as `approval.is_grandfathered()`. The requirement is not weakened for new charges. <br><br>⚠ **B7 applied to the download is OURS, not CC-2's** — recorded in §4c. An unapproved charge's attachment **views inline** and refuses only the raw download, through `approval.can_print()` rather than a second copy of the rule. <br><br>⚠ **"Reject before anything touches disk" is true of the STORE, not of the machine.** Werkzeug spools a large upload to its own temporary file while parsing the request, before any application code runs; that is upstream of every view here and cannot be intercepted without replacing the request stream factory app-wide. What is guaranteed is that an over-cap file never enters the attachment store and never gets a row. <br><br>⚠ **A `mysqldump` is no longer a complete backup.** The metadata rows are in the dump and the **files are not** — `backups/` and `attachments/` are two directories now, and a restore from the dump alone gives rows pointing at files that do not exist. First time this has been true of this application. ✅ **CLOSED 3 September 2026 (thirteenth pass), under the first §0 block of that date.** `tools/backup_db.py` now writes a **pair** under one stamp and one label — `<stem>.sql` and `<stem>-attachments.zip` — reading the store through `attachment.root()` so a relocated `ATTACHMENT_DIR` is followed rather than missed, storing paths **relative** to that root, and writing the zip **even when the store is empty** because an absent file cannot be told apart from a snapshot that failed. `--restore-attachments` is the other half: **additive**, and it re-validates every member against the root. **Proved by restore, not by a green test** — a nested file was planted, the pair taken, the whole directory destroyed, and the file came back at the same relative path with the same sha256. **13 tests** in [tests/test_backup_attachments.py](tests/test_backup_attachments.py), three of them mutation-checked against the source — and **one of those tests was VACUOUS as first written**, passing against exactly the absolute-path archive it forbade, which the mutation is the only reason anybody knows. <br><br>⚠ **The single-leg `tax_invoice_ref` gap is untouched** and is not B8's. | ☑ |

### 3C — measurement, labour cost and project result

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **C1** | order of working | **BUILT** | Both legs, refused **by URL**. `ra._c1_refusal()` gates `GET,POST /ra/create`: the installation leg needs an **approved** measurement on the BOQ's revision chain (`measurement.has_approved_measurement()`), the supply leg needs a delivery challan on it (`ra.challan_exists()`, reading `STORE["delivery_challans"]` directly). `/boq/view` draws each RA chip only when its step exists — **presentation, not the gate**. **21 tests** in [tests/test_c1_order_of_working.py](tests/test_c1_order_of_working.py), every one of them requesting the address directly and **including the POST**, because a GET refusal with an open POST is not a gate. Both guards were proved to fail when the guard was removed. <br><br>⚠ **THE SUPPLY LEG DID NOT EXIST BEFORE THIS PASS.** Nothing outside `challan.py` read `STORE["delivery_challans"]` — not `ra.py`, not the BOQ page — and `challan → ra` was refused at AST level. The previous edition's *"two unconnected documents rather than a chain"* was exactly right, and this is the whole of the link. `ra → challan` is now refused too: the existence check is a dict lookup, not a module. | Nothing for C1 as CC-2 words it. **Three things to know rather than discover:** ⚠ **Refusing by URL is OURS.** C1 states a domain model and no mechanism; B5's rule supplied it. ⚠ **The two legs are deliberately asymmetrical** — installation gets an ordering guard **and** a quantity ceiling, supply gets the ordering guard **alone**, because CC-2 puts no quantity on the challan arrow and `challan.BLOCK_OVER_DISPATCH` is False on purpose, so dispatch figures are a warning and not tight enough to cap somebody's money. ⚠ **The guard is on raising a NEW claim.** An existing bill keeps its typed quantity and renders; widening it would strand live records. §6-L. | ☐ |
| **C2** | measurement document | **BUILT** *(and most of it is OURS — read the next column)* | New module [measurement.py](measurement.py) and a `measurements` collection in [store.py](store.py) and [db.py](db.py). Six routes — `GET /measurement/`, `GET,POST /measurement/create?boq=`, `GET /measurement/view/<id>`, `GET /measurement/print/<id>`, `GET,POST /measurement/edit/<id>`, `GET,POST /measurement/delete/<id>` — the last two confirming on GET and writing only in the POST branch. Six permissions minted in `auth.PERMISSIONS`, eight endpoints classified in `auth.ROUTE_PERMISSIONS` (six routes plus B6's approve/reject pair). Fifth entry in `approval.DOCUMENTS`. **30 tests** in [tests/test_measurement.py](tests/test_measurement.py) and **19** in [tests/test_measurement_pin.py](tests/test_measurement_pin.py), among them the **hand-written GET-destroys-nothing test** ABOUT.md §7.9f requires of every new delete route — `tests/test_delete_methods.py` says in terms that its URL-map sweep cannot catch a both-verbs route that destroys on GET. <br><br>**Guard 1** — a measured quantity may not push its line past the BOQ quantity — `measurement.overmeasures()`, a **hard block** (unlike `challan.over_dispatched()`, which warns). **Guard 2** — cumulative claims may not exceed the approved measured quantity — inside `ra.overclaims()`, which already owns the cumulative arithmetic. **Nothing was reimplemented**: `ra.claimed_by_line()` stays the single place anything asks how much has been claimed, and only the number it is compared against moved. Six guards, each proved to fail with the guard removed. | ⚠ **FOUR THINGS HERE ARE OURS, NOT CC-2's, AND NONE IS DELIVERED C2.** CC-2's C2 is three lines — *"Raised from the BOQ. Approved measurements become the source of installation quantity on RA-Installation."* Ours: **(1)** that a measured quantity may not exceed the BOQ quantity; **(2)** that the ceiling is **cumulative across sheets** — stated per line, two sheets could each measure the whole of a line; **(3)** **which ladder** it climbs — B6 names charges and RA / Tax Invoice / PO and names measurement on neither, and the RA ladder was chosen because a measurement exists to feed an RA bill while the charges ladder ends at HR, who has nothing to say about what was measured on a site; **(4)** that it **prints at all** — CC-2 is silent, so the route exists but **no golden is pinned** and no letterhead was invented: the sheet is `docsheet.py`'s existing furniture plus two column widths and one signature label. All four are named individually in the fifth 29 August override block and are **unpriced**. ⚠ **The series is FY-scoped and deliberately NOT a `/settings` counter** — the challan has one because the client runs a paper challan book; nothing we hold says a measurement sheet is numbered from a book they keep. ⚠ **Purchase Manager holds none of the six**, as our reversible default, on the same terms as its existing absence of `ra.*`. | ☐ |
| **C3** | merged RA | **BUILT** | [merged_ra.py](merged_ra.py) (1,022 lines), 2 September 2026, under the **first override block of that date** — which is also the block that unblocked it, by answering **BQ2** and then **BQ1** ahead of any code. Own `merged_ras` collection; a separate document type, the Draft PO → PO relationship. One **issued** RA-Supply bill + one **issued** RA-Installation bill from the same revision chain, both rows sets **stacked** (never combined), totals **summed from what the two bills stored**. Mints `SF/MI/26-27/0001` from its own counter at **cap 16** (Rule 46(b)), derived from neither leg. Five pages plus two approval endpoints, the RA ladder, and the merge action on the RA register as CC-2 requires. **33 tests** in [tests/test_merged_ra.py](tests/test_merged_ra.py). ABOUT.md §3 (Merged RA). | ⚠ **The single-leg `tax_invoice_ref` gap is NOT closed** and was explicitly out of scope. An ordinary RA bill's field is still typed with no counter behind it, and `print_ra()` still falls back to `ref` and then to a string built from `ra_no` when it is blank — so DOMAIN.md §4.2's STATUS paragraph stands, annotated rather than replaced. A test pins it so C3 is not read as having closed it. <br><br>⚠ **`invoice.approve` was checked, not assumed.** The merged document carries `ra.approve`; both permissions reach the same three roles today, so the choice confers nothing, and a test fails the day that stops being true. <br><br>⚠ **`/merged/` is not on the nav or the launcher**, deliberately: CC-2 names the RA register as the merge action's home. Named in `UNLINKED_ON_PURPOSE` with that reason. **No print golden moved.** | ☑ |
| **C4** | employee master | **BUILT** | New leaf module [employee.py](employee.py) and an `employees` collection in [store.py](store.py) and [db.py](db.py). Fields: name, employee code, designation, **site** (an address-book link plus the label snapshotted), **day rate**, date joined, active flag. ⚠ **It was a MONTHLY salary and a free-text site until 30 August 2026; both were our errors and both are corrected under the third override block of that date** — see §4c row 11 and the two `⚠ CORRECTED` notes at the end of this row. Five routes — `GET /employee/`, `GET,POST /employee/new`, `GET /employee/view/<id>`, `GET,POST /employee/edit/<id>`, `GET,POST /employee/delete/<id>` — the last of which **confirms on GET and destroys only in the POST branch** (`9d060ee`'s shape), with its own hand-written GET test because `test_delete_methods.py` says in terms that its URL-map sweep cannot catch a both-verbs route that destroys on GET. Four permissions minted in `auth.PERMISSIONS` and five endpoints classified in `auth.ROUTE_PERMISSIONS`. **35** tests in [tests/test_employee.py](tests/test_employee.py), plus **22** in [tests/test_day_rate_pin.py](tests/test_day_rate_pin.py) and **27** in [tests/test_site_picker.py](tests/test_site_picker.py), both shared with C5. | Nothing for C4 as CC-2 words it — *"Employee details and salary"* is one sentence and this is the whole of it. **Three things to know rather than discover:** ✅ **The nav link and the dashboard card ARRIVED on 29 August 2026 (third pass).** The caveat that stood here — *"There is NO nav link and NO dashboard card, deliberately … the link is queued work, for a pass that expects to re-baseline the goldens"* — described the cost of protecting the goldens in an unattended pass, and that cost was that **the owner could not find a page he had paid for**. The pass it named arrived: five goldens moved +248 bytes each, in the `head` block alone, and nothing on any printed sheet changed. ⚠ **Owner, Director and HR only.** The *restriction* is spec-traced to B4 and marked `§` in the matrix; who *holds* it is still a derivation and marked `·`. Operation Head holds the wages ledger but not this — ours, and a checkbox if the client disagrees. ⚠ **The untagged item alongside it is NOT delivered** — HR's right to *edit* salary is outside C4 and outside MG/SF/2026-02. See §4a. <br><br>⚠ **CORRECTED 30 August 2026, and C4 STAYS BUILT.** Two facts about the client's own business were wrong on this record and neither was CC-2's fault. **(1) The rate is a DAY rate.** Samruddhi pays daily or weekly; the field is `day_rate` and `MAX_MONTHLY_SALARY` (₹10,00,000) became `MAX_DAY_RATE` (₹1,00,000), because a ceiling sized for a month catches almost nothing on a day — **that number is ours and CC-2 gives none**. **(2) The site is an address-book link**, not free text. ⚠ **NO STORED FIGURE WAS CONVERTED**: a monthly figure reread as a day rate is about twenty-six times too large, so every record that existed is **marked** (`rate_model: pre_day_rate`), the page says the rate needs re-entering, and `day_rate_of()` refuses to answer rather than answering wrongly. The set is **closed and counted** — 1 employee on this database — and `tests/test_day_rate_pin.py` fails if a record created after the migration carries the mark, which is `measurement.py`'s pre-measurement pin one register along. **A correction is not a bar: C4 was BUILT and stays BUILT.** | ☐ |
| **C5** | attendance and site-wise labour cost | **BUILT** | New leaf module [attendance.py](attendance.py) and an `attendance` collection in [store.py](store.py) and [db.py](db.py). Four routes — `GET /attendance/` (the day's muster + the site-wise cost, `?date=` moves the day), `GET,POST /attendance/mark`, `GET,POST /attendance/edit/<id>`, `GET,POST /attendance/delete/<id>` — the last of which **confirms on GET and destroys only in the POST branch** (`9d060ee`'s shape), with its own hand-written GET test because `test_delete_methods.py` says in terms its URL-map sweep cannot catch a both-verbs route that destroys on GET. Four permissions minted in `auth.PERMISSIONS` and four endpoints classified in `auth.ROUTE_PERMISSIONS`. **34 tests** in [tests/test_attendance.py](tests/test_attendance.py), plus the 22 and 27 shared with C4 and **18** in [tests/test_registers.py](tests/test_registers.py). <br><br>⚠ **THE OT MULTIPLIER IS A SETTING AND NO LITERAL MULTIPLIER IS IN THE CALCULATION CODE.** `settings.ot_multiplier()`, defaulting to the client's own 1×, with `/settings` saying on its face that the Factories Act and most state Shops & Establishments Acts put overtime at generally **twice** — CC-2's point being that hardcoding 1× makes this software compute a **statutory underpayment**. Held two ways: a behavioural test (change the setting, ₹1,250 becomes ₹1,500, and nothing stored is rewritten) and an **AST walk** over `daily_wage()`, `ot_amount()` and `cost_of()` that fails on any numeric constant in a multiplication or a division. `STANDARD_HOURS_PER_DAY` is a **name**, not a literal — CC-2's own `÷ 8`. <br><br>⚠ **One employee = one site = one day, enforced at WRITE time** in `conflicting_record()`, called by both write routes before anything is stored — not in the form. Keyed `(employee, date)` and **deliberately not** `(employee, site, date)`: the second reading bills one day's wage three times for one person marked on three sites. The edit route passes its own id as `except_id`, which is how this constraint is usually got wrong. | Nothing for C5 as CC-2 words it — five bullets, all five built. **Four things to know rather than discover:** ⚠ ~~**`wage_days_per_month` is a SECOND setting and it is OURS, not CC-2's.**~~ ✅ **RETIRED 30 August 2026 — there was never anything to divide.** The divisor existed to turn a monthly salary into a daily wage, on the reading that CC-2's `salary` was monthly. It is not: CC-2's own note calls `salary ÷ 8 × hours` **"1× ordinary rate"**, which is true only if `salary ÷ 8` is an HOURLY rate — so `salary` is a **day's** wage and 8 is the hours in a day. Read as a month, *"salary as 0 or 1 based on attendance"* pays a whole month for one day present, which is exactly the figure the owner was shown. ⚠ **The stale stored value on the live database was `1`**, which made a day's wage the entire monthly salary and is why the footnote on his screen read *"1 working days a month"*. The setting, the accessor, the field, the argument and the stored key are all gone; §4c row 11's neighbour was **removed** rather than re-argued. ⚠ **Site comes from the ADDRESS BOOK and is deliberately not a project** — a BOQ carries `project_name` *and* `site_location` as separate fields, `employee.site` is already free text by C4's choice, and a `project_id` here is the first half of C6. ⚠ **Overtime on an absent day is recorded, shown and NOT paid.** CC-2 does not rule on it; the hours stay visible so the contradiction is not swallowed. ⚠ **Owner, Director and HR only. Operation Head is REFUSED and marked `–`, not `§`** — ours, reversible at `/roles/edit/<id>`. See §4b. <br><br>⚠ **A MARKING CARRIES A `project_id` FROM 30 AUGUST 2026 (ELEVENTH pass), AND IT IS NOT C5 AS CC-2 WORDS IT.** C5's five bullets name no project; this is **§4c row 22**, priced nowhere, and nobody may cite it as delivered CC-2 scope. It exists because the ninth pass's address fold left `'Bangalore, Karnataka'` carrying **four** projects, so the site stopped being a strong enough key to attribute labour. `charge.py`'s two keys — an id somebody picked and a snapshotted name — with the picker **filtered to the projects at the marking's own site**: one preselects, **several require a choice**, none saves blank, and a project at another site is dropped and never stored. ⚠ **Absent means LEGACY, not "no project"**, and `tools/backfill_marking_projects.py` is the bulk mapping — it linked **8** markings on the live database and would have refused to guess for any at a multi-project site. **C5 was BUILT and stays BUILT; a field is not a bar.** | ☐ |
| **C6** | project profit and loss | **BLOCKED** | No project P&L exists, and the project page **refuses to be one by design**: *"no revenue total, no cost total, no margin, no profit, no net, no balance … it does not do the subtraction"* [projectview.py:21-26](projectview.py#L21-L26) &mdash; ⚠ **that docstring moved from lines 11&ndash;15 on 30 August 2026 and its wording is UNCHANGED**; route `GET,POST /projects/view/<id>` [projectview.py:289](projectview.py#L289). ⚠ **The page carries a SITE LABOUR section (§4c rows 19 and 23) and it is not a P&L.** From 30 August 2026 (eleventh pass) it renders **two labelled groups** — *Booked to this project*, found by the `project_id` §4c row 22 put on the marking, and *At this site, unattributed*, the legacy rows found through the address — **summed separately and never added together**. Each group adds its own one column up the way five panels already did; **two sums inside one panel is still one panel**, and the prohibition on a figure combining two **panels** is untouched. **No margin, no project total, no net, and no choice between the two labour bases.** ⚠ **Attribution is not costing.** Knowing which project a day was worked for does not say whether that day's *cost* is the attendance wage or the BOQ installation base rate, which is the whole of Open question 4 — so C6 is **exactly as blocked as it was**, and the pass that answers the question now has a cleaner input rather than an answer. The only margin arithmetic in the app is `purchase.job_cost()` [purchase.py:280](purchase.py#L280), which is scoped to a **quotation**, not a project, and ignores recorded charges entirely. Blocked on the labour-cost authority decision; see §5. | The decision first. Then: planned margin from the BOQ against actual cost from POs and charges, and an explicit reversal of `projectview.py`'s standing prohibition — that docstring is a deliberate guard and must be amended, not ignored. | ☐ |

---

## 4a. Built, and in NO phase — extra purchase-order lines

⚠ **THIS IS NOT ONE OF CC-2's TWENTY ITEMS, AND NOTHING BELOW TOUCHES THE BARS
IN §2.** It has its own section for exactly that reason: a row in §4 would put
it on the board, and it does not belong there. **The denominator is still 20.**

| | |
|---|---|
| **What** | Extra **free-text** lines on a purchase order — parts the client needs from a vendor that appear nowhere on the BOQ. |
| **Tag** | **None.** No 3A, no 3B, no 3C. |
| **Priced** | **NOWHERE.** Not in MG/SF/2026-01 (it did not exist), not in MG/SF/2026-02 (untagged — and that quotation **lapsed on 28 August 2026**). |
| **Authorised by** | The **29 August 2026** OVERRIDE block in `CLIENT_CHANGES.md` §0, which records it as new unpriced scope and forbids counting it toward the board. |
| **Status** | **BUILT** — but "built" here means *delivered*, not *paid for* and not *inside a phase*. |

**Why it is untagged.** The client asked for it **after** the 19 August 2026
meeting that produced CC-2's twenty items. It therefore belongs with the five
lines in CC-2's *"Stated by the client, NOT in MG/SF/2026-02"* section — said in
a meeting, absent from both the tagging and the quotation — except that those
five are **not built** and this one now is. That is the whole reason this
section exists rather than a footnote.

⚠ **The commercial decision has NOT been taken.** Whether this is charged,
absorbed, or folded into a replacement for the lapsed MG/SF/2026-02 is the
client-facing owner's call and has not been made. **No agent may invent a price
for it, record it as delivered under either quotation, or record it as a §0
no-charge exemption** — that exemption covers defect and reachability fixes
against scope already sold under MG/SF/2026-01, and this is new capability.

**What was built.** `extra_lines` on the purchase order record, beside
`line_items` and `charges`. `_parse_extra_lines()`, `extra_lines_of()`,
`extra_lines_total()` and an `extra_lines` parameter on `_totals_of()` in
[purchase.py](purchase.py); `.xl-*` in `PURCHASE_STYLES`; the repeater on
`/purchase/create` and `/purchase/edit/<id>`; rendered as ordinary item rows by
`view_purchase()`. A new bottom-of-graph module [po_parts.py](po_parts.py)
holds the seeded **prefill** list. **52** tests in
[tests/test_po_extra_lines.py](tests/test_po_extra_lines.py) (33 when it was
built, +19 in the second pass of 29 August 2026), of which
`test_the_worked_example` is the load-bearing one.

⚠ **THE PREFILL IS PERFORMED BY THE SERVER, and it was not on the day this was
built.** *(Second pass, 29 August 2026 — a finding the building pass recorded
against its own work.)* The seeded rate reached the form only through
`xlFill()`, so the feature **did not exist with JavaScript disabled, broken, or
never executed** — and never executed is what the repo actually does: there is
no JS harness here and adding one was not authorised, so `xlFill()`, `addExtra()`
and `recalc()` were asserted only as **strings present in the response.**

Worse, the page carried **`xlNorm()`, a JavaScript reimplementation of
`po_parts._norm()`, with nothing checking that the two agreed.** The day they
diverged, the box would prefill a rate the server then declined to mark as a
placeholder, and **an invented price would reach a vendor with no chip on it**
— the exact failure the chip exists to prevent.

The halves are now inverted. `_parse_extra_lines()` fills a blank rate and unit
from `po_parts.py` **on POST**, so the whole feature is reachable by the ordinary
pytest suite; the browser gets `PP.prefill_map()`, which is `po_parts.INDEX`
flattened, and does **one dictionary lookup** on it. There is no second
implementation of "matches" to drift, `xlNorm()` is gone, and a lookup the
browser misses the server still fills. **A blank box only** — an explicit `0` is
a figure somebody chose and survives untouched.

⚠ **The map handed to the browser was also built from `PARTS` alone, so it
carried canonical names ONLY** — not one of the client's own spellings ever
prefilled, on either form. Fixed by the same change.

**Three concepts now live on the PO record and the code says so in as many
words**, because conflating them is the defect this shape exists to prevent:

| | what it is | where it enters |
|---|---|---|
| `line_items` | BOQ/catalogue lines; carry a `line_id` | `subtotal` |
| `extra_lines` | **new** — free-text parts; carry **no** `line_id` | `subtotal` |
| `charges` | A3's 4-slot labelled repeater | after `subtotal`, into `taxable_value` |

An extra line is a **line**, not a charge: it is goods we are buying from this
vendor. Routing it through `charge_totals()` would produce the right grand total
by the wrong route — and print 2,100 rupees of parts under the totals as though
the vendor were billing us a fee. The worked-example test asserts that
counterfactual rather than describing it.

⚠ **Every seeded rate is an ASSUMED PLACEHOLDER and none of it is a quoted or
verified price.** The client sent his list with **no prices and no units**;
`po_parts.py` exists so an order can go out before the vendor has priced it, and
every figure is expected to be overwritten. A line still carrying one is flagged
on screen with an amber chip reading **"placeholder · not quoted"** that is
**`display:none` at print** — the vendor receives the order, not our note that
we invented the price. **Nobody may present one of these figures as a real
price**, in code, in the UI, or to the client.

⚠ **`rate_is_assumed` means *this is the placeholder figure*, not *this was
prefilled*.** It is true when the server supplied the rate **or** when the
submitted rate is exactly the seeded one — one arithmetic test covering both
limbs, derived on the server and never trusted from a hidden field. So typing a
seeded part and its seeded rate by hand **is** flagged, although nobody
prefilled it: a human who types the placeholder from memory has invented a price
just as surely as the server has. The wording was chosen to be true in that case
too — it is a claim about the **figure**, never about the operator — and the
over-reporting is the safe direction, because the mark never prints and the
opposite error would let an invented rate travel unmarked.

⚠ **OPEN QUESTIONS FOR THE CLIENT — now two, and both pinned by tests.** *Is
"PO red paint" red-oxide primer?* It is most likely `P.O. Red` or `R.O. Red` on
his sheet, seeded **verbatim** and deliberately **not renamed** — guessing would
put a word in the client's mouth on a document that goes to a vendor, and on a
purchase-order screen "PO" also reads as "purchase order". The second question —
*are `200mm elbow` and `8" elbow` the same part?* — arrived with the alias
cutback below, which removed the ambiguity rather than answering it.

**Recorded deviations**, both deliberate:

1. **No repeater on `/purchase/from-boq/<boq_id>` or
   `/purchase/from-draft/<draft_id>`.** Those are picker flows over a schedule;
   a free-text surface on a picker is a second design. A part on no schedule is
   added afterwards on the edit form, exactly as a charge is. **The same call A3
   made, made again.** Both routes still write `extra_lines: []`.
2. ~~**`quotation.py`'s deal panel folds extra-line value into `Committed` with
   no breakout row.**~~ ✅ **CLOSED, 29 August 2026, second pass.**

   > **The finding as first recorded, unchanged:** *"`purchase.job_cost()`
   > reports `extra_committed` and `extra_count` on a row of their own and
   > `/purchase/view` renders it, but the deal panel **re-derives its own
   > `committed`** rather than calling `job_cost()`, and `quotation.py` is
   > frozen against feature work ([INTRODUCTION.md §7](INTRODUCTION.md)).
   > Recorded rather than changed."*

   ⚠ **The missing row was the symptom. The defect was two functions computing
   the same commercial word**, and that is what was fixed: the panel now calls
   `job_cost()` and computes nothing of its own. The breakout follows for free,
   as a fourth `.jc-cell` reading **"Of which, extra parts"**, drawn only when
   there is extra-line value — the same rule `/purchase/view` uses for the same
   clause. `.jobcost-grid` is already `repeat(auto-fit, minmax(120px,1fr))`, so
   it needed **no new CSS**.

   `quotation.py` was **unfrozen NARROWLY** for it, by the client-facing owner,
   under the second 29 August 2026 override block. The freeze is otherwise
   intact and `product.py` is untouched.

   ⚠ **MEASURED BEFORE THE CHANGE, on the §6-D precedent, with a stop
   condition.** A Committed figure that moves is one somebody may already have
   quoted to a client, so the rule was: **if any figure moves, stop and report,
   do not ship.**

   - **Live database: 3 quotations, 2 purchase orders, and ZERO POs carrying a
     `quotation_id`.** So 0 figures move — **out of a population of 0.** The
     job-costing block does not render for any record in that database, and the
     honest reading is that **the live data cannot evidence this either way.**
     Recorded as such rather than as a clean bill, because "0 differ" and "0
     were comparable" are not the same sentence.
   - **Supplemented, because 0-of-0 earns nothing.** Three POs swept across all
     eleven statuses — the six real ones plus missing, blank, lower-case,
     upper-case and unknown — is **1,331 combinations**, and nine shapes of
     `grand_total` (absent, `None`, `""`, `0`, int, float, numeric string,
     negative, whitespace). The two derivations disagreed on **0** of them and
     raise the **identical** exception on the one malformed input.

   Held by five tests in `tests/test_po_extra_lines.py` §11, and by
   `tests/test_nav_user_chip.py`, which now asserts every edited line in
   `quotation.py` falls inside `view_quotation()`.

### The alias cutback — a DEFECT FIX against this section's own work

⚠ **CLOSED 29 August 2026, third pass, and it is still outside the bars.**
Repairing untagged work does not make it tagged, and the fix is a §0
**no-charge** item: a defect against something delivered the same day, not new
capability. **It does not retro-price the extra-lines work either** — that
remains priced nowhere.

**The finding, measured rather than described.** `po_parts.py` shipped with 73
canonical parts and **172 aliases, of which 156 nobody had written**. They were
plausible-looking permutations generated to widen the prefill — word order
reversed, a space added, `mm` swapped for `inch`. Three classes were actively
wrong, and the first is a live wrong number:

| class | example | what it did |
|---|---|---|
| **a live wrong number** | `200 mm elbow` → ₹3,400 · `200 mm elbow 8 inch` → ₹3,200 | one physical part, two placeholder rates, **and which one landed on a purchase order depended on how somebody typed it** |
| **an inch↔mm equivalence** | `25mm flange` → `1 inch flange` | a **pricing decision dressed as a spelling**, taken inside a lookup table where nobody would read it |
| **a bare name choosing a size** | `grinding wheel` → the 4-inch one | a rate for a part the operator did not specify |

`_norm()`'s own docstring already said why: *a match it gets wrong puts a
figure on a purchase order that nobody chose.* The aliases were that same
mistake one level up from the normaliser the sentence was written about.

⚠ **One deleted alias rested on a MISREADING of the client's sheet**, and it is
named in the module, in ABOUT.md §2h and in a test so it is not put back: his
sheet carries a **dummy** flange — `6 inch dummy flange 16mm (240 PCD)` — and,
separately, `150mm flange`. `6 inch flange → 150mm flange` folded a dummy
flange into a plain one.

**Measured before and after:**

| | before | after |
|---|---|---|
| alias entries | 172 | **16** |
| `INDEX` keys | 241 | **89** |
| keys that were neither a canonical name nor a client line | **153** | **0** |
| hit-rate against the client's own lines | 77 / 78 | **78 / 78** |

⚠ **The hit-rate went UP, and that row is not a typo.** The cutback removes the
surface for strings **nobody wrote** and adds one the client did: his verbatim
`M.S ANGEL 50 X 50 X 5 MM - 03 pcs` had never been indexed, only the form with
the quantity stripped. Against arbitrary typing the prefill now misses far more
often — `grinding wheel` fills nothing, the line is accepted exactly as typed
with a blank rate and no assumed flag — **and every string it stopped answering
for is a string nobody wrote.**

**The rule, made permanent, and the test is the deliverable.** An alias may
exist only if the client wrote that exact string. `CLIENT_LINES` holds his 78
strings and is the source of truth; `CLIENT_LINE_QUANTITIES` is the one
permitted derivation, **a table of two rows with the stripped form written out**
rather than a regex that would decide for itself what a quantity is; and
`MISSPELLINGS` records why a canonical departs from his spelling and **licenses
no alias on its own** — reading it as "any string containing `soket` may be an
alias" is how 156 of them arrived. `permitted_alias_keys()` is the rule as code
and [tests/test_po_parts_aliases.py](tests/test_po_parts_aliases.py) **calls it
rather than carrying a copy**, which is the `xlNorm()` lesson one file along.

⚠ **NO CANONICAL PART WAS MERGED OR SPLIT.** `200mm elbow` and `8" elbow` stay
two entries with **no alias between them**, so typing one can never fetch the
other's rate. The module does **not** assert they are the same part and does
**not** assert they are different.

⚠ **THE CLIENT'S SHEET IS NOT IN THIS REPOSITORY, and that is the weakest part
of this work.** Not `client_docs/`, not `fixtures/`, not the history — it
arrived as a message and was transcribed straight into `PARTS`, so `PARTS` is
now the only record of it anywhere. `CLIENT_LINES` is therefore a
**reconstruction from the module's own evidence**, and every line carries its
grade in the source: `(v)` verbatim from the original docstring or commit
message, `(m)` a canonical with a documented misspelling reversed, `(—)` taken
as the canonical because nothing records anything else. A test fails if a line
is added without a grade. **The tests hold `PARTS` to `CLIENT_LINES`; nothing
can hold `CLIENT_LINES` to the sheet.**

⚠ **The count is 78 distinct strings — 80 raw lines**, two of them exact
repeats. **A figure of 81 has been quoted elsewhere and cannot be reproduced
from anything in this repository.** The missing line, if there is one, left no
trace in the transcription.

⚠ **No existing test was rewritten, weakened or deleted for this**, and the
reason is worth keeping: the twelve aliases pinned by
`test_an_alias_prefills_the_same_rate_as_its_canonical_name` **all survive the
cut**. That is independent corroboration — the surviving set is the set the
pass that built the file already treated as the client's own.

**Open questions carried forward to the client, both pinned by tests:**

1. **Is "PO red paint" red-oxide primer?** Seeded verbatim, deliberately not
   renamed. Unchanged from the previous edition.
2. **Are `200mm elbow` and `8" elbow` the same part?** 200 mm is 8 inches, so
   they may be one item written twice at two placeholder rates — or two items
   he buys separately. **This pass removed the ambiguity rather than answering
   it**, which is the only arrangement that cannot put the wrong figure on an
   order.

## 4b. Untagged and NOT built — the open item beside C4

⚠ **HR's right to EDIT salary is outside C4 and outside MG/SF/2026-02.** CC-2
records it in *"Stated by the client, NOT in MG/SF/2026-02"* as item 3: *"HR —
salary editing, inside employee details. Not tagged. HR editing salary appears
nowhere in MG/SF/2026-02. C4 covers an employee master carrying salary; it does
not cover HR's right to edit it."*

**It is not built and this row is not a work order.** What C4 shipped is an
employee master carrying salary, and HR holds `employee.edit` on it — for the
engineering reason that a register somebody can read but nobody can maintain is
not a master. ⚠ **That is not the untagged item being delivered.** The untagged
item is a *commercial* question about who may change a person's pay and what it
costs to answer; the permission grid is editable on `/roles/edit` and settles
nothing about the price. If the client raises it, it needs pricing, not code.

The other four untagged lines CC-2 carries — the two "visual dashboard" requests
and the Accountant's employee overview and employee management — are **also not
built**, and items 4 and 5 are the ones to watch now that an employee master
exists: they will look one checkbox away and they are not.

### Operation Head and `employee.*` — REFUSED as a reversible default

**Ruled on 29 August 2026 by the client-facing owner, second pass, and recorded
in the second override block of that date in `CLIENT_CHANGES.md` §0.**

**Operation Head does not hold `employee.view`, `employee.create`,
`employee.edit` or `employee.delete`.** The seeded role does not grant them and
did not gain them; `auth.py` was **not edited** to reach this position — it is
where the role already stood, now stated rather than left implicit.

✅ **It is a REVERSIBLE DEFAULT, not a policy.** An Owner grants any of the four
at **`/roles/edit/<id>`** with a checkbox — **no code change, no deployment, no
developer and no re-login.** A question the client has not been asked is
correctly held as a default that is free to change, and refusing *for now* costs
nothing to undo. **Nobody may record this as the client having decided
anything.**

⚠ **CC-2 does not settle it — and "CC-2 is silent on this role" would be the
wrong reason.** It is worth stating precisely, because the imprecise version is
the one that gets repeated:

- **B4 names the role.** *"Director (×2), Operations Head, HR, Sales Manager,
  Purchase Manager, Accountant."* Operations Head is one of the six.
- **B4's one sentence about employee data does not name it.** *"HR information
  is restricted from Sales, Purchase and Accounts."* Operations Head is not in
  that sentence **in either direction** — neither granted employee access nor
  denied it.
- **CC-2 mentions the role elsewhere**, and none of it touches employee data:
  B6's approval ladder (*Director → Operations Head → HR* on charges;
  *Operations Head + Director* on RA / Tax Invoice / PO), and the untagged
  *"Operation Head — visual dashboard"* line among the five items with no home.

So the refusal is **ours**, and `docs/ACCESS_MATRIX.md` marks it as such: those
four cells carry the new **`–` (withheld by our derivation)** mark rather than
`§`, because a `§` would claim a backing that does not exist. **The three roles
B4 does name keep their `§`** — for Sales, Purchase and Accounts that sentence
is real, and their twenty-four withheld cells are a specification being applied.

⚠ **No grant moved.** `auth.py` is byte-identical, Operation Head holds the same
39 permissions it held before, and the only change to the matrix is those four
cells' **marking** plus the legend row that gives the new mark meaning.

#### ⚠ The same ruling now covers `attendance.*` — 29 August 2026, third pass

**Operation Head does not hold `attendance.view`, `attendance.create`,
`attendance.edit` or `attendance.delete`**, and those four cells carry the same
`–` mark for the same narrow reason: B4 names the role, B4's one sentence about
employee data does not name it in either direction, and a `§` would claim a
backing that does not exist. It stays **39 permissions**.

It is **a reversible default and the code proves it rather than claiming it**:
`test_operation_head_can_be_granted_it_without_a_code_change` ticks
`attendance.view` onto `role-operation-head` in memory and requires
`/attendance/` to open — no deployment, no developer, no re-login.

⚠ **Note where the line actually falls, because it is not obvious.** Operation
Head **does** hold the whole of `charge.*`, the wages and site-expense ledger.
So the refusal is a line drawn at **pay-derived** data — the master, and now a
muster that carries a salary snapshot and produces a wage — rather than at site
cost. **That line is ours.** Sales, Purchase and Accounts keep their `§` on the
new rows too, because for them B4's sentence is real and a muster producing a
wage is HR information on the same terms the master is.

---

## 4c. Built beyond CC-2 — the register

**⚠ This is a REGISTER, not a revision.** Nothing here is removed, re-argued,
downgraded or defended. Every entry was disclosed by the pass that built it and
is recorded in a `CLIENT_CHANGES.md` §0 override block; this section pulls them
into one list so the question *"what did we build that nobody specified?"* has a
single answer instead of five blocks to read.

**Why it exists.** These items were scattered across §0 override blocks, one
pass each, and a fact that lives in five places is a fact nobody can total. The
risk is specific and commercial: somebody presents a subsystem to the client as
delivered CC-2 scope, or prices a phase against a quotation that never covered
it. **Nobody may cite anything below as a delivered CC-2 requirement, or as work
MG/SF/2026-02 covers.** Building each was the right call — that is argued in the
blocks and is not re-argued here — and it does not make any of it specified.

**Chargeability, stated once for the whole table.** Every item below is priced
**nowhere at all**. It is not §0's MG/SF/2026-01 exemption, which covers defect
and reachability fixes against scope already sold; and it is not MG/SF/2026-02,
which prices the CC-2 items these things sit beside but not the things
themselves. **MG/SF/2026-02 is in any case expired and unsigned.**

Passes are lettered as the override blocks order them: **A** extra PO lines and
C4, **B** the prefill and the narrow `quotation.py` unfreeze, **C** C5, the
navigation re-baseline and the alias cutback, **D** B6 and B7, **E** C2 and C1 —
all five dated 29 August 2026 — **F** the cleanup pass, **G** the day rate, the
site picker and the two register screens, **H** the project→site link and the
address-book guards, **I** the Site Labour section, the live data cleanup
and the demo scenario tool, and **J** the marking→project link, the two-group
Site Labour panel and the backfill that maps the unambiguous ones — all five
30 August 2026.

| # | What was built | Sits beside | Pass | Why it is ours |
|---|---|---|---|---|
| 1 | **`approval.can_modify()` and every edit rule in it** — approved is locked, a part-climbed ladder is locked, a rejected document returns to its creator alone, an unstarted one is its creator's | B7 | **D** | B7 governs **printing and downloading only** — *"an unapproved document may be viewed, but not printed or downloaded"*. It says nothing whatever about editing. The whole subsystem fills that silence. |
| 2 | **B7's print gate narrowed by two named exceptions** — a **draft** RA bill prints carrying its DRAFT overprint, and a **cancelled** one prints | B7 | **D→E** | Read strictly, B7 took away two things the client does today. The overprint *is* the safeguard B7 wants, and a cancelled bill is the audit record of a withdrawn claim rather than a claim. Raised by D, answered by E's override block. |
| 3 | **A rejected DRAFT prints** — the exemption is checked before the rejected clause | B7 | **E** | Lifecycle state and approval state are orthogonal, and the block's wording admits both orderings. The ordering is a choice we made. |
| 4 | **A measured quantity may not exceed the BOQ quantity for its line** (`measurement.overmeasures()`, a hard block) | C2 | **E** | C2 is three lines and states no ceiling of any kind. Without it the sheet is a form that records a number nobody checks. |
| 5 | **The measured ceiling is cumulative across sheets** | C2 | **E** | Stated per line, two sheets could each measure the whole of a line. C2 says nothing about accumulation. |
| 6 | **Which approval ladder a measurement climbs** — the RA ladder | C2 | **E** | B6 names ladders for charges and for RA / Tax Invoice / PO, and names measurement on **neither**. The RA ladder was chosen because a measurement exists to feed an RA bill, while the charges ladder ends at HR. |
| 7 | **That a measurement sheet prints at all, and what it looks like** | C2 | **E** | C2 is silent on printing. The route exists; **no golden is pinned** and no letterhead was invented, deliberately, so the client's first sight of it is not a re-baselining exercise. |
| 8 | **The measurement series is FY-scoped and not a `/settings` counter** | C2 | **E** | The challan has a counter because the client runs a paper challan book. Nothing we hold says a measurement sheet is numbered from a book they keep. |
| 9 | **C1 is enforced BY URL rather than by hiding a control** | C1 | **E** | C1 states a domain model and no mechanism. B5's established rule supplied one. |
| 10 | **The two C1 legs are asymmetrical** — installation gets an ordering guard **and** a quantity ceiling, supply gets the ordering guard alone | C1 | **E** | CC-2 puts no quantity on the challan arrow, and `challan.BLOCK_OVER_DISPATCH` is False on purpose, so dispatch figures are a warning and not tight enough to cap somebody's money. |
| 11 | **Where a `site` comes from, and that it is deliberately not a project** — free text under pass C, an **address-book picker** under pass G | C4 / C5 | **C → G** | CC-2 never says where a site comes from. Free text was our answer and it was the wrong one: the live data spelled one place more than one way, and a labour cost split across two spellings is wrong while both halves look right. The picker is our answer now, ⚠ **and so is every rule around it** — that only `site` and `office` addresses are offered (a vendor is somebody we buy from), that an existing string is matched only on an EXACT label and otherwise left, marked and reported, and that near misses are printed and never applied. ⚠ A `project_id` here is still the first half of **C6**, which is BLOCKED — **and an address does not join to a project either**, which is recorded in ABOUT.md rather than solved. |
| 12 | **Overtime on an absent day is recorded and shown, and not paid** | C5 | **C** | CC-2 does not rule on it. The hours stay visible so the contradiction is not swallowed silently. |
| 13 | **Operation Head is refused `employee.*` and `attendance.*`** — marked `–` in the access matrix, not `§` | C4 / C5 | **A / C** | B4 states exactly one restriction — HR information is kept from Sales, Purchase and Accounts — and names Operations Head in **neither** direction. A reversible default, changed with a checkbox at `/roles/edit/<id>`. §4b carries the ruling. |
| 14 | **Purchase Manager is refused all six `measurement.*`** | C2 | **E** | B4 says nothing either way. They carry `dc.*` because dispatch is theirs; a measurement feeds an installation claim. A reversible default on the same terms as row 13. |
| 15 | **`measurement.can_delete()`** — a sheet an installation claim rests on cannot be deleted | C2 | **F** | C2 says nothing about deleting a sheet. Deleting one lowers the ceiling under a claim already raised; the issued figures do not move but the project's remaining balance does. |
| 16 | **A project's site is an ADDRESS-BOOK LINK** — `site_address_id` is the join, `site_address` is demoted to the label snapshot, the form is a picker with no free-text fallback, and a legacy string is left, marked and required to be picked before it saves | C6 (adjacent) | **H** | ⚠ **CC-2 contains no item for this at all.** C6 — *"project profit and loss"* — is the item that would eventually want the join, and **C6 is BLOCKED** on Open question 4. Building the join is **not** building C6 and nobody may present it as such. `site_address` was free text, which is why the live data spelled one place two ways on three of the four projects; a project's site is a **join key** and free text cannot join. ⚠ **And so is every rule around it:** that only `site` and `office` addresses may be a site, that an existing string is matched only on an **exact** label and otherwise gets an address created **verbatim, misspelling included**, that near misses and duplicate pairs are printed and never applied, and that the snapshot and the live label are never silently reconciled — the amber band reports it. |
| 17 | **The address book's integrity guards** — delete refused while referenced with the records named as chips, an archive beside it, an edit log keyed on **user id**, and `type` locked while referenced | *(nothing)* | **H** | ⚠ **CC-2 contains no item for the address book at all**, and neither does MG/SF/2026-01. The book has been a master six collections point into since long before this pass and had **no delete guard whatever**; deleting a row dangled every reference silently. ⚠ **Whether that is a DEFECT the client is owed for free is a commercial question, it is the client-facing owner's, and it has NOT been taken** — it is recorded in the §0 block instead. The archive exists because *a delete-refusal with no archive is a trap rather than a guard*, which is `measurement.can_delete()`'s own finding (row 15) applied one register over. |
| 18 | **The site→project ambiguity is COUNTED and not guarded** | C6 (adjacent) | **H** | The client has said *one project = one site*; he has **not** said one site = one project, and the live data already has two projects on one string. `tools/backfill_project_sites.py` prints the count per address. ⚠ **No guard is built on it, deliberately** — it is evidence for the pass that answers Open question 4, and a constraint invented here would be one CC-2 never stated. |
| 19 | **A SITE LABOUR section on `/projects/view/<id>`** — every attendance marking whose `site_address_id` equals the project's, with date, employee, status, OT hours, day rate, overtime and total, a per-panel sum, and two distinct empty states | C6 (adjacent) | **I** | ⚠ **CC-2 has no item for a labour section on the project page.** C6 — *"project profit and loss"* — is the item that would eventually want a labour figure there, and **C6 is BLOCKED on Open question 4**. This section answers that question in **no direction**: it presents markings, does no subtraction, and states no margin, project total or net. It reuses `attendance.marking_cells()` rather than rendering a second row, and takes **rendered cells and never the arithmetic** — a second module able to compute a wage is a second place the OT multiplier could be hardcoded. ⚠ It lifted two standing prohibitions, both named in the override block rather than discovered by a test failure: ABOUT.md §5's *"none on `/projects/view/<id>`"* clause, and `attendance.py` being imported by nothing. |
| 20 | **`tools/clean_site_data.py`** — folds ONE named duplicate address, maps the unmapped `Banglore` strings, purges five named test records, and **refuses any purge that would orphan a document** | nothing | **I** | ⚠ **There is no CC-2 item and no MG/SF/2026-01 item for cleaning up a development database.** It exists because pass H created two address records for one place, **verbatim and deliberately**, and printed the pair as a duplicate it would not fold — recording that the resolution was *"a HUMAN's to resolve"*. This is that human resolving it, in writing, before it ran. ⚠ **It is not a merge engine**: every label is a module constant, there is no threshold, no similarity function and **no `--force`**. ⚠ **It refused one of its own five purge targets on the live database** — deleting project *"Banglore"* would have stranded delivery challan 3, measurement sheet `SF/MS/26-27/0001` (the only one that exists) and draft PO `SF/DPO/0003`. The project is still there and **whether those documents are disposable is a decision nobody has taken.** |
| 21 | **`tools/seed_demo_scenario.py`** — two sites, one project on each, three employees on confirmed day rates and eight markings across three days including one absentee | nothing | **I** | ⚠ **No CC-2 item, and it bends a standing rule that is NOT relaxed.** `tests/test_hardening.py` classifies `employees` and `attendance` as **transactional** — a seeded employee is a person who does not exist carrying a salary they are not paid, and a seeded marking invents a day's labour cost — and every word of that still stands. What makes this defensible is that it is **not part of the application**: nothing imports it, the writing is behind an explicit flag, a fresh install is still empty of both, and a test walks every module in the repository root and fails if one so much as names it. ⚠ **It does NOT create a third project sharing a site.** The site→project ambiguity (row 18) is real on this database and a fixture that manufactured another would make a live data problem look like an artefact. |

⚠ **ROWS 22, 23 AND 24 ARE PASS J's — 30 August 2026, ELEVENTH pass — AND ROW
22 IS THE ONE TO READ TWICE.** It puts a **project key on C5's records**, which
is the entry somebody could most plausibly mistake for C6 having started, and
row 20's own note is the reason it had to: pass I's fold left one address
carrying **four** projects, so a marking booked there answered for all four.
**Attributing a day is not costing a project.** Open question 4 asks *which
labour figure is authoritative* — attendance wages or the BOQ installation base
rate — and knowing which project a day was worked for answers none of it. **The
board does not move for any of the three, and C6 is BLOCKED exactly as it was.**

| # | What was built | Sits beside | Pass | Why it is not CC-2, and what it does not do |
|---|---|---|---|---|
| 22 | **`project_id` + `project_name` on an attendance marking**, with the form picker **filtered to the projects at the marking's own site** — one preselects, several **require** a choice, none saves blank, and a project at another site is dropped and never stored | C5 (extends) / C6 (adjacent) | **J** | ⚠ **CC-2's C5 is five bullets and not one of them names a project**: presentee/absentee, salary as 0 or 1, *one employee = one site = one day*, `OT = (salary ÷ 8) × hours`, and a presentation table of *Employee — Site — OT time*. The field exists because **the site is not a strong enough key to attribute labour** — row 20's fold concentrated four projects on one address. It is **`charge.py`'s shape and not a second one**, and `STORE["projects"]` is read directly with `attendance → project` refused at AST level, exactly as `charge → project` is. ⚠ **Absent means LEGACY, not "no project"**, no third state marker is invented, and nothing on a render path backfills one. ⚠ **It answers Open question 4 in no direction** and no margin, project total or net is built. |
| 23 | **The Site Labour section reads it** — two labelled groups on `/projects/view/<id>`, *Booked to this project* and *At this site, unattributed*, **summed separately and never added together**, with the ambiguity note now **conditional** on the unattributed group being non-empty | C6 (adjacent) | **J** | ⚠ **Row 19's section, corrected rather than extended.** Row 19 said every row was booked at the site and tagged to no project; half of that stopped being true when row 22 shipped, so the panel splits and each group says which it is. **Two sums inside one panel is still one panel** — `projectview.py`'s first sentence, which five panels already exercise — and its prohibition on a figure **combining two panels** is untouched. ⚠ **The note now has to earn its place:** where every marking is attributed it is dropped, because a page that goes on warning about a resolved ambiguity teaches its reader to ignore the warning. The two groups come from `attendance.py`'s own readers, so *"attributed"* has one definition. |
| 24 | **`tools/backfill_marking_projects.py`** — links a marking where its site carries **exactly one** project, and **prints every other one with its candidates named** | nothing | **J** | ⚠ **No CC-2 item, and its refusal is the deliverable.** Zero or several projects at the site and the marking is left alone; it **never takes the oldest and never takes the newest**, because a wrong automatic match puts a day's labour cost against a project nobody chose and **looks exactly like a right one** — `po_parts.py`'s 156 invented aliases in a third register. Two tests name the tie-breaks somebody will be tempted to add. Dry-run default, `--write`, idempotent, before/after inventory, and the ambiguous report deliberately **does not go quiet on the second run**. ⚠ **On the live database it linked 8 and left 0 ambiguous** — not because the ambiguity is gone but because no marking is booked at the four-project address. Its hard case is proved by its tests, not by this data. |
| 25 | **B7's gate applied to an attachment's DOWNLOAD** — an unapproved charge's supporting file **views inline** and refuses only the raw download, through `approval.can_print()` | **B8**, and B7 | **K** | ⚠ **CC-2 SAYS NOTHING ABOUT A DOCUMENT'S SUPPORTING FILE.** B7 gates an unapproved *document* against being printed or downloaded; the attachment is not the document. Leaving the supplier bill downloadable while the charge built from it is not would be a hole big enough to drive the whole document through — photograph the attachment and you have every figure on the charge. So the consistent reading was taken, and it is recorded as **ours** in the same style as B7's own four judgement calls in `can_modify()`. ⚠ **It CONSUMES B7's function rather than restating it.** A second copy of the rule would have to be kept in step with the two named print exemptions, the grandfather clause and the rejected case, and would not be — `test_the_download_gate_calls_b7_rather_than_restating_it` walks the AST to hold that. ⚠ **The permitting half is asserted as hard as the refusing half.** An unapproved attachment must still VIEW, or the gate would be over-applying B7 rather than applying it — CC-2's B7 is explicit that an unapproved document *may be viewed*. ⚠ **A receipt's attachment is not gated at all**, and that is a fact about `approval.DOCUMENTS` having no `receipt` entry rather than an exemption written into `attachment.py`: if a receipt ever joins the ladder, the gate starts applying with no change to that module. |
| 26 | **`sha256` on every attachment record**, and `attachment.orphan_files()` | **B8** | **K** | ⚠ **Neither is in CC-2's B8**, which asks for filename, path, size, type and the parent record. The digest is what makes a silently swapped or truncated file detectable later; without it a corrupted supporting document is indistinguishable from a good one, which is the same class of failure as the BLOB corruption B8 was redesigned to avoid. `orphan_files()` exists because `delete_one()` **deliberately tolerates** a file it cannot unlink — a file locked by a virus scanner or an open viewer must not leave a ledger row pointing at a document the operator has been told is deleted — and a tolerated failure mode that is not findable is a leak. Nothing in the application calls it; it is reached from a shell and from one test. |

⚠ **ROW 27 IS PASS L's — 3 September 2026, THIRTEENTH pass — and it is the only
one that pass adds.** Its other two items are **defect fixes against work
delivered on 2 September 2026** and are therefore **not** §4c entries at all:
this section's standing sentence is explicit that its contents are *not* §0's
MG/SF/2026-01 exemption, and that exemption is exactly what covers them. The
attachments half of the backup and `claimed_by_line()`'s merged walk are both
repairs to something already built, and putting a repair in a register of
unspecified scope would inflate the register and understate the exemption at the
same time.

| # | What was built | Sits beside | Pass | Why it is ours |
|---|---|---|---|---|
| 27 | **A minted statutory serial on a SINGLE-LEG RA bill** — `ra.next_tax_invoice_ref()`, series **`RI`**, `SF/RI/26-27/0001`, its own counter at `_TAXREF_CAP = 16` under Rule 46(b), FY-scoped, max+1, minted in `create_ra()` when the field is left blank and never at print | **C3** (adjacent), and DOMAIN.md §4.2 | **L** | ⚠ **CC-2 CONTAINS NO ITEM FOR THIS.** C3 is *the merged RA*, and the 2 September block that authorised it said in terms that the single-leg gap was **out of its scope** and would need a block of its own. The requirement is **DOMAIN.md §4.2's** — *the two number series are not the same counter* — which this application has carried since Phase 2 and satisfied only **in part**: the prohibition held wherever an operator typed the field and failed silently wherever they did not, because `print_ra()` fell back `tax_invoice_ref` → `ref` → a string built from `ra_no`. ⚠ **The series letter is ours.** CC-2 names none; `RI` was chosen so that three counters — `TI` (`invoice.py`), `MI` (`merged_ra.py`) and this — cannot put one statutory serial on two documents, which is the failure Rule 46(b) exists to prevent. ⚠ **So is the decision that a TYPED VALUE STILL WINS**, on the reading that an operator may be transcribing a serial out of a book the client keeps; nothing we hold says they are or are not. ⚠ **And so is leaving the historical set alone.** 6 of the 7 live bills carry a blank field and **3 of those are ISSUED**; they go on printing a `ref`-derived number, which is still what §4.2 forbids. Replacing an issued document's number silently — or printing a dash where one used to be — is the act the max+1 discipline prevents, so the set is **counted and closed** exactly as `pre_measurement` and `created_by` were, and **whether any is backfilled is the owner's decision**, reserved in the §0 block, which authorises no backfill tool. |

⚠ **THIS PASS REMOVED A ROW AND ADDED NONE — 30 August 2026, eighth pass.**
The retired entry was:

> | 11 | **`settings.wage_days_per_month`** — the divisor turning a monthly
> salary into a daily wage, defaulted to **26** | C5 | **C** | CC-2 never gives
> a divisor. 26 is the usual convention and 30 is defensible, and **they give
> different money**. Stated as ours on the page itself. ⚠ Still an open
> question. |

It is kept here verbatim rather than deleted, because **how it went is the
point**. The entry was honest about being ours and honest that the choice was
open — and the correct answer to *"we invented this"* turned out to be **taking
it out**, not defending it or re-tuning it. CC-2's `salary` was a **day rate**
all along: its own note calls `salary ÷ 8 × hours` *"1× ordinary rate"*, which
is true only if `salary ÷ 8` is an hourly rate. There was never anything to
divide. The setting, the accessor, the form field, the calculation argument and
the stale stored value are all gone, and `tests/test_day_rate_pin.py` fails if
any of them comes back.

📌 **A register of things we built beyond the specification is most useful when
entries can LEAVE it.** One that only ever grows records that we kept adding;
this one now records that we took something away. The fifteen that were here
before pass H are unchanged and none was re-argued.

⚠ **Row 15 (was 16) closed a hole rather than opening scope.** Pass E shipped
the delete route with the gap recorded in the route's own docstring and carried
it into its report as an open question. It is in this register because CC-2 is
silent on it, exactly like the fourteen above, not because the cleanup pass
built a feature.

⚠ **ROWS 16, 17 AND 18 ARE PASS H's, AND THEY WERE THE LARGEST SINGLE ADDITION
THIS REGISTER HAD TAKEN.** That is the point of writing them here rather than
letting them read as C6 groundwork. Row 16 sits *adjacent to* C6 and **does not
deliver any part of it**; row 17 sits beside **nothing at all** — there is no
CC-2 item for the address book, and no MG/SF/2026-01 item either; row 18 is a
number, recorded so the pass that answers Open question 4 does not have to
re-derive it. **The board does not move for any of the three.**

⚠ **ROWS 19, 20 AND 21 ARE PASS I's, AND ROW 19 IS THE ONE TO READ TWICE.**
Rows 20 and 21 are tools that touch no client-facing capability at all — they
repair and populate a **development** database. **Row 19 puts a reading of C5's
data onto a page it has never appeared on**, and that is the entry somebody
could most plausibly mistake for C6 having started.

**It has not.** C6 is *"planned margin from the BOQ against actual cost from
purchase orders and recorded charges, with the difference shown"*, blocked on
whether attendance wages or the installation base rate is authoritative. Row 19
shows **neither a difference nor an authority**: it lists markings, adds its own
one column up the way five panels on that page already did, and says on its face
that the rows are booked at a **site** and not tagged to the project. ⚠ **Three
passes running have now added to this register without moving a bar**, and that
is the register working rather than the board being stuck.

### What is NOT in this register, and why

- **The extra purchase-order lines (§4a) and the alias cutback that repaired
  them.** They are not *beyond CC-2*; they are **outside CC-2 entirely** — no
  3A/3B/3C tag, requested after the 19 August meeting that produced the list,
  and priced in neither quotation. §4a is their register and it is deliberately
  a separate one, outside the bars and outside the denominator.
- **Tests, tools and guards.** `tools/reconcile_role_permissions.py`, the
  reachability walk, the vacuity floors and the doc-figure pins are engineering
  on work already sold, not capability delivered to the client. They are
  unpriced in the same way a `.gitignore` is.
- **Anything on the bars.** Every one of the seventeen BUILT items is CC-2's
  own, and this section changes none of their statuses. **The board does not
  move for anything written here.**

---

## 5. BLOCKED

### ~~C3 — merged RA · blocked on BQ1, which is blocked on BQ2~~ — **UNBLOCKED AND BUILT, 2 September 2026**

> ⚠ **RESOLVED. Kept rather than deleted, because the way it was resolved is
> the point and because this section is what a later reader will find first.**
>
> Both questions were answered by the client-facing owner in the **first
> `CLIENT_CHANGES.md` §0 block of 2 September 2026**, **BQ2 first and BQ1
> second**, which is the order this section itself insisted on — and **ahead of
> any code**, which is the other thing it insisted on. Neither was resolved
> inside a build step, and the merged document does **not** reuse a leg's number.
>
> **BQ2's answer splits the question rather than picking a side:** `ref` is our
> document number and keeps its 64 characters; `tax_invoice_ref` is the statutory
> serial, is a **different field**, and does inherit Rule 46(b)'s 16. The two
> sections of `PHASE4_RA_DESIGN.md` were never arguing about the same field.
>
> **BQ1 then dissolves:** the two legs never spent a statutory serial, so there
> is no third one to reconcile. The merged document mints its own, from its own
> counter, in a series (`MI`) chosen so it cannot collide with `invoice.py`'s
> `TI`.
>
> ⚠ **What is NOT resolved, and is not claimed to be:** a **single-leg** RA
> bill's `tax_invoice_ref` is still a typed field with no counter, still falling
> back to `ref` and then to `ra_no`. The conflation this section names below is
> therefore **still live on every unmerged bill**. It was out of C3's scope and
> needs a block of its own.
>
> The record below is left exactly as it stood.

**Confirmed still unresolved as at 25 August 2026.** Not resolved by this pass,
deliberately.

**The decision:** which of three tax-invoice numbers is the statutory serial
when a merged document is raised over two source bills that each already carry
one — and, prior to that, whether `ref` is a statutory serial subject to Rule
46(b)'s 16-character cap at all.

**Owner:** the client-facing owner (Manas), in the C3 design pass. Explicitly
**not** the client — CC-2 records that MG/SF/2026-02 3C.02 already sold the
merged document as carrying one tax invoice number, so putting it to him now
would be asking permission for something already committed. Not an agent's to
take either.

**The contradiction, by file and line:**

| Where | What it says |
|---|---|
| [DOMAIN.md:347](DOMAIN.md#L347) §4 | The RA bill **is** a tax invoice. |
| [DOMAIN.md:418](DOMAIN.md#L418) §4.2 | The tax invoice number is a **separate series** and must not be derived from `ra_no`. |
| [DOMAIN.md:405](DOMAIN.md#L405) | Marks this **part** built — both numbers print, but the Tax Invoice No. is a typed field, not a series. |
| [PHASE4_RA_DESIGN.md:166-168](PHASE4_RA_DESIGN.md#L166-L168) §2 | *"**If** the RA bill is the tax invoice … `ref` inherits Rule 46(b): unique within the FY and **≤ 16 characters**"* — and calls the condition unresolved. |
| [PHASE4_RA_DESIGN.md:328](PHASE4_RA_DESIGN.md#L328) §5 | *"`ref` is our document number, not a tax-invoice serial; **no 16-character cap**"* — the same file answering the other way. |
| [PHASE4_RA_DESIGN.md](PHASE4_RA_DESIGN.md) §5/§7, `[AMENDED 8 Aug 2026]` | Rules that the RA bill **is** a tax invoice — satisfying §2's antecedent while §5's conclusion, written earlier, still denies the consequent. |
| [STATE.md:326](STATE.md#L326) §2.1 | Dead-Premise Cleanup Checklist **REOPENED 23 August 2026**, `PHASE4_RA_DESIGN.md` left un-ticked pending exactly this. |

**The code sides with §5 and enforces nothing at 16** — verified this pass:
`_REF_CAP = 64` [ra.py:219](ra.py#L219), passed as `cap=_REF_CAP`
[ra.py:856](ra.py#L856), against `cap=16` [invoice.py:190](invoice.py#L190)
through the same `P.fy_ref()` whose docstring names Rule 46(b) as the reason the
parameter exists [pipeline.py:196-201](pipeline.py#L196-L201). The dead premise
is still stated in code at [ra.py:216-218](ra.py#L216-L218) — *"this document is
not one"* — and whoever answers BQ2 must correct it.

A 16-character budget cannot be retrofitted: `SF/RA/26-27/0004` is at exactly 16
with no room for a merge marker, so a capped merged serial cannot be a decorated
variant of either leg's number. **Answer BQ2 before BQ1.**

### C6 — project P&L · blocked on the labour-cost authority decision

**The decision:** which is authoritative for labour cost — attendance-based
wages (C5) or the installation base rate on the BOQ. Subtracting both counts
labour twice.

**Owner:** the client. This is `CLIENT_CHANGES-2.md` **Open question 4**, still
open, and it is a question about how their own costing works rather than a
design consequence of anything we sold. It is not one of the BQ questions and
must not be settled internally.

C5 can be built without the answer. **Wiring C5 into C6 cannot.**

⚠ **C5 is now BUILT, and C6 is exactly as blocked as it was.** Nothing changed
about this decision on 29 August 2026 — what changed is that the module whose
figures would feed it exists, which makes the wiring look one function call
away. It is not: **the question is which of two labour bases is authoritative,
and it is the client's.**

⚠ **AND A PASS DID ADD A LABOUR SECTION TO THE PROJECT PAGE — 30 August 2026,
TENTH pass — SO THE SENTENCE THAT USED TO END THIS PARAGRAPH NEEDS ANSWERING
RATHER THAN DELETING.** It read, verbatim:

> A pass that "just adds a labour line to the project page" has answered Open
> question 4 on the client's behalf.

**That is still true of the thing it describes, and it is not what was built.**
The distinction is the whole of why C6 stays BLOCKED, and it is worth stating
precisely because the warning was aimed at exactly this shape of work:

| what the warning forbids | what row 19 does |
|---|---|
| a **labour cost** for the project | a **list of markings** booked at the project's **site**, which is not the same set and the page says so |
| a figure that could be **subtracted** from anything | a per-panel sum of one column, beside five panels that already had one. No margin, no project total, no net |
| an implicit answer to *which labour base is authoritative* | **no** base is asserted. The section carries no BOQ installation figure at all, so there is nothing for it to have chosen between |
| attribution of a site's labour to a project | the opposite, **on the face of the page**: it names the other projects on the same site, says the money appears on their pages too, and says which project a day's labour belongs to **cannot be determined from this data** |

⚠ **The two prohibitions that were lifted are named, not quietly dropped:**
ABOUT.md §5's *"none on `/projects/view/<id>`"* clause, and `attendance.py`
being imported by nothing. Both are recorded in the fifth `CLIENT_CHANGES.md` §0
block of 30 August 2026, the import guard is now an **allowlist of exactly one**
rather than deleted, and `projectview.py`'s own margin / total / net prohibition
is **untouched**. The dashboard card still carries counts and no money, and
`charge.py` is still forbidden in both directions.

⚠ **Open question 4 is not one line of work away from being answered — it is
still a question for the client**, and the section that now exists makes that
*more* visible rather than less: a reader who opens *Sify Bangalore* sees three
other projects on the same address and is told the data cannot say which of them
a day's labour belongs to.

⚠ **A PROJECT NOW JOINS TO AN ADDRESS, AND C6 IS STILL EXACTLY AS BLOCKED —
30 August 2026, ninth pass.** This is the entry most likely to be misread, so it
is stated in terms. C6 had **two** obstacles, not one:

1. **an address did not join to a project at all** — recorded in ABOUT.md §4 and
   pinned by a test. ✅ **Closed.** `projects.site_address_id` is the link.
2. **which labour base is authoritative** — Open question 4. 🔴 **Untouched, and
   it is the one that blocks.**

Closing (1) makes C6 *possible to build once (2) is answered*. It does not
answer (2), it is not part of C6, and **PROGRESS.md §4c row 16 is where it is
registered — as work beyond CC-2, sitting adjacent to C6 and delivering none of
it.** ⚠ **The muster's half of the roll-up is still missing on purpose:** an
attendance marking names a *site*, a project now names a *site*, and joining
those two would attribute one site's whole labour cost to every project standing
on it. ⚠ **The live data now has FOUR projects on one address**, not two: the tenth
pass folded the duplicate spelling, which **concentrated** the ambiguity rather
than removing it. That count is printed by `tools/backfill_project_sites.py` and
by `tools/clean_site_data.py`, and rendered on `/projects/view/<id>` — **three
places report it and not one of them resolves it.** A constraint invented here
would be one CC-2 never stated.

### Phase-wide gate — not an item status

Distinct from the two above, and deliberately kept out of the per-item column:
**MG/SF/2026-02 is sent and unsigned**, and the `CLIENT_CHANGES.md` §0 gate
applies to `CLIENT_CHANGES-2.md` in full. Every one of the twenty items is
gated from being *started* regardless of the status recorded against it. The
tables above report what the code does, not what may be worked on.

---

## 6. CODE vs DOCS

Recorded, not fixed. Nothing in this section was corrected in this pass.

**A. A6's latest-bill-only restriction is real, was RULED CORRECT on 28 August
2026, and is now A6's stated limitation.** *(Updated. The finding below stands
exactly as recorded; what is added is the ruling and the client-facing wording.)*

✅ **The ruling, taken under the 28 August 2026 override block.** The restriction
**stays**. RA bills are cumulative — `claimed_by_line()` sums the whole chain —
so editing bill 3 while bill 5 exists corrupts every claim downstream of it,
including figures already sent out. The client asked for "edit and delete in RA"
without qualification because the chain arithmetic is not his to know.
`claim_is_frozen()` → `is_latest_bill()` is **correct behaviour, not a
shortfall**, and A6 therefore closes **BUILT with a stated limitation** rather
than being lifted or left PARTIAL.

**The limitation, in language that can be read to the client as it stands:**

> *You can edit or delete the most recent RA bill on a project while it is still
> a draft. You cannot edit or delete an earlier one once a later bill exists,
> because every later claim was worked out from the earlier one — changing it
> would silently change every bill after it, including ones already sent to the
> main contractor. To correct an earlier bill, cancel the bills after it and
> then it, newest first, and reissue; cancelling keeps each number and records
> why. If the correction can wait, put it on the next claim, where the
> contractor can see it.*

**Arbitrary-bill editing is NEW SCOPE.** It is priced nowhere and nobody may
record this limitation as a defect owed to the client.

**What changed in code, and it is only this:** `frozen_reason()` and
`can_delete()`'s frozen branch now explain *why* and name cancelling forward as
the supported route. The wording deliberately keeps the phrase
`tests/test_ra_routes.py` already pins, so no existing test was retargeted.
[tests/test_ra_edit_delete.py](tests/test_ra_edit_delete.py) drives edit and
delete end to end through the routes and pins the limitation **as** a limitation.

**The original finding, unchanged:**

`CLIENT_CHANGES-2.md` A6 narrows the client's unqualified "edit and delete in
RA" to **draft only** and says nothing further. The code adds a second
narrowing that CC-2's requirement line does not carry: `can_edit()` refuses via
`claim_is_frozen()` [ra.py:1495](ra.py#L1495), and `can_delete()` refuses with
*"Only the latest bill can be deleted"* [ra.py:1553](ra.py#L1553), both
resolving to `is_latest_bill()` [ra.py:1407](ra.py#L1407), which compares
`ra_no` against the highest on the BOQ. So a **draft that is not the highest
`ra_no` is refused both operations.** CC-2's own note already flagged this as
the obvious candidate for work A6-as-sold may still cover; this pass confirms it
is true of the code. Covered by
`test_a_bill_with_a_later_bill_after_it_cannot_have_its_claim_edited`
[tests/test_ra_routes.py:392](tests/test_ra_routes.py#L392) and
`test_a_mid_chain_bill_cannot_be_deleted`
[tests/test_ra_routes.py:786](tests/test_ra_routes.py#L786) — the restriction is
deliberate and tested, not an oversight.

Consequence worth knowing before the commercial call is made: nothing prevents
RA2 being raised while RA1 is still a draft, and cancelled bills remain in
`bills_of()`, so a **cancelled** later bill also freezes an earlier draft. The
restriction is reachable in ordinary use, not theoretical.

**B. Tag numbering diverges between CC-2 and the quotation, and the repo has
already tripped on it.** CC-2 lists 3C as C1–C6. The quotation tag `3C.02` is
used throughout the repo to mean the **merged RA**, which is CC-2's **C3** —
[CLIENT_CHANGES-2.md:401](CLIENT_CHANGES-2.md#L401),
[CLIENT_CHANGES-2.md:427](CLIENT_CHANGES-2.md#L427),
[DOMAIN.md:425](DOMAIN.md#L425), [DOMAIN.md:438](DOMAIN.md#L438).
[DOMAIN.md:354](DOMAIN.md#L354) writes it as *"3C / **3C.02**"*, conflating the
two schemes inside one citation. MG/SF/2026-02's 3C list evidently omits C1 —
which is a statement of the domain model rather than a deliverable — putting the
two schemes one apart for every 3C item from C2 onward. 3A does not diverge:
`3A.06` and CC-2's A6 are the same item. **This file tags by CC-2's own letters
throughout**, per the rule that CC-2 is the only source for what the items are.
Anyone carrying a `3C.0n` tag over from the quotation must add one to reach the
CC-2 letter.

**C. `CLIENT_CHANGES-2.md`'s header says "not started. Nothing in this file is
built."** *(Corrected in part on 26 August 2026; **more wrong than ever after
27 August**, when A1, A2 and A5 were built and A4 re-verified.)* That is [CLIENT_CHANGES-2.md:5](CLIENT_CHANGES-2.md#L5). It is wrong
by this audit: A4 is built and tested, and A1, A5 and A6 each stand partly on
shipped code. CC-2's own A6 section already contradicts its header by
documenting three built routes. The header was not amended when that section was
added on 23 August 2026.

**D. The client register presented Outstanding with no caveat — HALF CLOSED on
27 August 2026, and the half that remains is the one that matters.**

~~CC-2's A4 note says the figure is only as correct as the A5 write-off field
makes it, and *"do not quietly present the figure as authoritative"*. A5 does
not exist, and `client.py` renders the figure with no qualification beyond an
*"in credit"* note when it is negative.~~

✅ **The presentational half is closed.** A5 now exists, `outstanding_of()` and
the register both net it off, and `client.OUTSTANDING_CAVEAT` states under the
figures that Outstanding is an internal figure and that no credit note stands
behind a write-off. Pinned by
`test_the_page_no_longer_presents_outstanding_without_a_caveat`
[tests/test_client_outstanding.py](tests/test_client_outstanding.py).

✅ **The arithmetic half is CLOSED, 28 August 2026 — and the count came before
the decision.** The previous edition listed three possible answers and said each
of them *"restates figures somebody may already have quoted to a client"*. That
was the right worry and it turned out to have nothing behind it.

**The live database was queried before anything was changed: ZERO
adjustment-mode receipts.** One receipt in the whole database, mode `neft`. So
**no historical figure moved by a rupee**, and the question that had been held
open as a data question had no data behind it.

**What was done.** `received_val` in `client._client_groups()` now excludes
adjustment-mode receipts via `ra.is_adjustment()`, so **Received** is bank
movements only.

⚠ **An adjustment is excluded from Received and is NOT dropped.** It is
subtracted from Outstanding under its own **Adjusted** heading, shown on the
same terms as A5's write-off row — where there is one, absent where there is
not. **This is a deliberate deviation from the instruction that authorised the
pass**, which specified `outstanding = billed − received − written_off` with
`received` payment-only; that arithmetic would have put every adjustment back
into Outstanding. Two facts in this repo say it should not:
`ra.py`'s note on `RECEIPT_MODES` states that an adjustment is settled against
the bill and *"the money genuinely stops being outstanding"*, and the tripwire
itself asserted in as many words that `total_outstanding == 0.0` was **right**
and only Received was wrong. Dropping the adjustment would have fixed Received by
breaking the figure the tripwire called correct. Three sums, three facts — the
same call A5 took when it made `write_off` a separate field.

**Outstanding is invariant by construction, not by luck:** `received_val` lost
exactly the receipts `adjusted_val` gained.

**`ra.outstanding_of()` and `ra.received_against()` were deliberately NOT
changed.** They are the *bill's* figures, not the register's columns, and
`test_an_adjustment_still_reduces_what_is_outstanding_on_the_bill` pins that the
two sides of the fact still agree. `ra.is_adjustment()` is one function rather
than six string comparisons for that reason.

**The tripwire did its job and is retargeted**, not deleted:
`test_an_adjustment_mode_receipt_still_inflates_received` is now
`..._no_longer_inflates_received`, with all three of its old assertions kept
verbatim in a comment above it. Only one of the three changed, 100000.0 →
90000.0.

**E. ~~`charge.py` is named for a module it is not~~ — CORRECTED and CLOSED,
29 August 2026.** *(The finding below stands exactly as recorded. What is added
is what was done about it, and why the fix is as narrow as it is.)*

> **The original finding, unchanged:** *"`charge.py` is named for a module it is
> not. Its title is "Employee & Miscellaneous Charges Ledger"
> [charge.py:2](charge.py#L2) and the dashboard card reads "Employee & Misc
> Charges" [dashboard.py:1614](dashboard.py#L1614). There is no employee record
> behind either. Anyone auditing C4 by name will find these and conclude an
> employee master exists. It does not."*

✅ **It does now, which is what forced this.** C4 shipped a real employee master
in the same pass, and a title that was merely loose became **actively
misleading**: two things in the application would have answered to "employee",
one of which knows nothing about employees. `charge.py`'s `person` is **free
text somebody types**, not a person the system holds.

**What changed, and only this:** the module docstring, and the dashboard card
label — now **"Expenses & Charges"**. The docstring records the old title, why
it was wrong, and that `person` stays free text.

⚠ **THE MODULE WAS NOT RENAMED, and that is a decision rather than an
oversight.** `charge.py`, `charge_bp`, `/charge`, `STORE["charges"]`, the
`charges` table and `charge.*` in `auth.PERMISSIONS` are all unchanged. A rename
would reach the route registry, the access matrix, the dashboard,
`projectview.py` and every test naming an endpoint — a wide change, for a word,
in a pass authorised for two specific things. **What was wrong was the
description, so the description is what changed.**

✅ **The third site is now closed too — 29 August 2026, second pass.**

> **What the first pass recorded, unchanged:** *"One further site was found and
> deliberately LEFT: [projectview.py:434](projectview.py#L434) still renders
> `<h2>Employee & Misc Charges</h2>` over the charges block on a project page.
> It is outside the two sites the pass instruction named, and `projectview.py`
> was not otherwise touched here. Recorded rather than silently fixed or
> silently ignored — it is a one-line change for whoever next opens that
> file."*

It now reads **"Expenses & Charges"**, matching the label already chosen for
the dashboard card and `charge.py`'s title, with a comment beside it saying why.
**The label only.** `projectview.py` is **not** renamed and nothing else in that
file was touched — the same call §6-E made about `charge.py` itself, made again
one file along. The page's "Person" column still shows free text somebody typed,
which is the fact the wording was hiding.

With all three sites corrected, **nothing in the application labels this ledger
"employee" any more**, and an auditor checking C4 by name can no longer land on
the wages ledger and conclude the employee master was built twice.

⚠ **Note what is still true after the correction:** `charge.py` remains where
wages actually get recorded, and it is **not** linked to the employee master.
That link is **C5** and it is gated; `employee.py ↔ charge.py` is forbidden in
both directions at AST level to keep it that way.

**F. `projectview.py` carries a standing prohibition that C6 requires be
reversed.** [projectview.py:21-26](projectview.py#L21-L26) forbids the page from
showing any figure that exists only by combining two panels — *"no revenue
total, no cost total, no margin, no profit, no net, no balance"* — because *"the
moment it does, the project page becomes a P&L that nobody signed off on."* C6
is that P&L. Not a contradiction today, but the guard is deliberate and must be
amended in the same pass that builds C6, not silently overridden.

⚠ **The line numbers moved on 30 August 2026 (11&ndash;15 → 21&ndash;26) and the
WORDING DID NOT.** The tenth pass added a Site Labour section to that page and
left this docstring exactly as it stands, which is the distinction the whole
entry turns on: the prohibition's **first** sentence — *"Each panel shows the
documents' OWN values and adds that one column up"* — is what the new panel's
sum exercises, alongside the five that already did. The prohibition is the
**second** sentence, on a figure that exists only by combining two panels, and
nothing on the page combines two. **This entry is not closed and C6 still
requires it be reversed.**

**G. `ra.py` still states the dead premise in code.**
[ra.py:216-218](ra.py#L216-L218): *"No 16-character cap. That is Rule 46(b)'s
limit on a TAX INVOICE number, and **this document is not one**."*
[DOMAIN.md:347](DOMAIN.md#L347) §4 and PHASE4_RA_DESIGN.md's
`[AMENDED 8 Aug 2026]` note both rule that it **is** one. Already tracked as
row 3 of [STATE.md:494](STATE.md#L494); restated here because BQ2 cannot be
closed without correcting it, and C3 cannot start without BQ2.

**H. ~~A3 is stopped on a tax question~~ — ANSWERED and CLOSED, 28 August 2026.**
*(The finding below stands exactly as recorded on 27 August. Stopping was the
right call and the record of why is kept.)*

✅ **The ruling: the charge is INSIDE the taxable value.** The document is a
purchase order **we issue to a named vendor**. A line on it is part of what we
are agreeing to pay *that vendor*, which is consideration for that vendor's
supply — s.15(2)(c) CGST Act, incidental expenses. **The third-party reading
below describes a cost that would not appear on this vendor's PO at all**; it
would be a separate transaction with a separate party on a separate document,
and `charge.py`'s expenses ledger — whose "Transport / Freight" head the finding
cites — is exactly where it lives. The ambiguity is real in the world and is not
real on this document.

✅ **The exception is expressible anyway**, which is what stops this ruling
having to be reopened. Every charge line carries `taxable`, defaulting to
**true**; an untaxed line is added after the tax and never before it. The
finding's own objection — *"the same head is one thing on one order and the
other thing on the next"* — is answered by putting the flag on the **line**
rather than on the head in `/settings`, which is where the finding correctly
says it does not belong.

**The arithmetic, in one place** — `_totals_of()`:

    subtotal      = sum(line totals)              lines only, meaning unchanged
    taxable_value = subtotal + taxable charges    A3 enters HERE
    tax           = _tax_lines(taxable_value)
    grand_total   = taxable_value + tax + exempt charges

`create_purchase()` had a verbatim copy of those three lines and now calls
`_totals_of()` instead, because A3 has to enter the arithmetic in one place or
the create form and the reprice form compute a different base from one order.

⚠ **One part of CC-2's A3 note was NOT built:** the heads are not seeded in
`/settings` and not editable there. Recorded as a deviation in the 28 August
override block. **The original finding follows, unchanged:**

CC-2's A3 specifies **one repeater, "label + amount"**, with the heads seeded in
`/settings`. A label and an amount carry **no taxability**, and on a **buy-side**
purchase order a loading, unloading or transportation line is one of two
completely different things:

- **Part of the vendor's own consideration** — s.15(2)(c) CGST Act, incidental
  expenses charged by the supplier in respect of the supply. It is **inside** the
  taxable value and attracts tax at the line rate.
- **A third-party cost we carry ourselves** — our own tempo, our own labour at
  site. It is not part of this vendor's supply at all, it is **outside** the
  taxable value, and it may be a GTA reverse-charge liability this document has
  no way to express.

**The same head is one thing on one order and the other thing on the next**,
depending on who performs the work — so a per-head flag in `/settings` does not
settle it either, it only moves the question.

**There is nothing in this repo to read the answer off.** `grep` finds no
`freight`, `packing`, `round_off` or `other_charge` on any document in the
application; **no document this app prints carries a charge line today.**
`charge.py`'s heads serve the expenses ledger, which computes no tax at all —
and its "Transport / Freight" head is itself evidence for the *second* reading,
because a cost booked in an expenses ledger is by construction not the vendor's.

**Why this was stopped rather than decided.** An inflated taxable value on a
purchase order overstates the input tax credit we tell a vendor to bill us for,
and their invoice then does not reconcile against ours. That is not a defect
testing finds. Contrast **A2**, which was built: a discount is *before tax under
both readings of CC-2's wording*, so the tax base is invariant across the
ambiguity, and that invariance is what made it safe.

**Owner: the client-facing owner, with the client.** The question is one
sentence — *"on a purchase order, is a transportation or loading charge
something the vendor is being asked to bill us for, or something we pay
somebody else?"* — and Yogesh can answer it. It is not one of the BQ questions
and must not be settled internally.

**I. ~~A1 ships Draft-only~~ — the narrowing was LIFTED on 28 August 2026, and
this entry is CLOSED.** *(The finding below stands exactly as recorded.)*

✅ **The commercial question the finding said "has not been asked" was asked and
answered.** `can_edit_rates()` now refuses **only** `Cancelled`. The reasoning
that overturns the narrowing: the reason anybody wants an editable base rate is
that a wrong rate has **already gone out**, so restricting the unlock to Drafts
leaves exactly that case unsolved and removes the feature's purpose — a Draft
rate was never locked, it is a form nobody has submitted.

✅ **The objection the narrowing protected is answered, not discarded.**
`update_purchase()`'s *"a vendor has already been told a price and a quantity,
and changing them behind the document is how a dispute starts"* is still true —
and the dispute starts when the change is **invisible**, not when it is made. So
every reprice that moves a figure writes a `reprice_log` entry: who, when, and
old rate → new rate on each line that actually moved, rendered under the order.
Only moved lines are listed; a submit that changes nothing writes nothing and
says so. The trail sits inside `.po-panel`, which is `display:none` at print —
what the vendor holds is the order, not our record of having changed it.

⚠ **`Cancelled` is still refused, and that is not a lifecycle narrowing.** A
withdrawn order is not a live order; repricing it would restate a document we
have said is void — the same rule `ra.cancelled_reason()` states for a cancelled
bill.

**Four tests asserted the narrowing and were rewritten**, each keeping its old
assertion verbatim in a comment. **The original finding follows, unchanged:**

`purchase.can_edit_rates()` allows `status == "Draft"` and refuses the other
five. The reason is sound and is the code's own: `update_purchase()` refuses
commercial edits because *"a vendor has already been told a price and a
quantity, and changing them behind the document is how a dispute starts"*, and
`PO_STATUSES[0]` is **`Draft` — "written, not yet sent to the vendor"**, which
is precisely the case that reasoning does not cover.

**But the reason being sound is not the same as the narrowing being sold.**
CC-2 A1 reads "PO base rate editable" and its note reads "straightforward field
unlock" — no lifecycle qualification anywhere. This is the same shape as A6's
narrowing, and CC-2 says of that one that it *"must be explained to him rather
than silently applied"*. The same applies here and has not been done.

A1 is therefore recorded **PARTIAL** rather than BUILT, on the same principle
that holds A6 there: the code does less than the requirement line says, however
good the reason. Marking it BUILT would quietly assert a commercial answer.

**J. `/purchase/edit/<id>` is gated by `purchase.create`, not `purchase.edit`.**
*New, 27 August 2026. A deliberate classification, recorded because it reads
oddly until the reason is known.*

`purchase.edit` is labelled *"Update a purchase order's status"* and that is what
it means. Repricing changes what this company has agreed to **pay a vendor**,
which is the authority `purchase.create` already confers — somebody who can
raise a PO already chooses every rate on it — and a strictly larger authority
than marking a delivery received.

Every role holding `purchase.edit` today also holds `purchase.create`, so **the
grid does not move** (it was 7×61 when this was written and is 7×79 now); the classification is for the day a storekeeper is
given status rights and must not be able to reprice an order. **No permission
was minted**: inventing one would force a per-role decision CC-2's B4 does not
authorise an agent to take on the client's behalf, and B4 states exactly one
restriction (HR information away from Sales, Purchase and Accounts) and no grid.

**K. A classified page with no link is a page nobody finds — FOUND by sweep,
CLOSED 29 August 2026, third pass.** *New.*

The employee master shipped on 29 August 2026 correct, tested and permissioned,
with **no nav entry and no dashboard card**, to protect the print goldens during
an unattended pass. `test_there_is_no_nav_link_and_no_dashboard_card` existed to
stop that being "fixed" by accident and told the pass that adds the link to
delete it. **Its cost was that the owner could not find a page he had paid
for**, which is a delivery defect and not a presentation one.

**Enumerated before anything was changed**, which is how two more were found.
41 classified GET endpoints take no path argument; excluding forms their own
register offers and the pre-session and chip-hung session pages, **three** pages
were reachable and unlinked:

| endpoint | inbound `url_for` | verdict |
|---|---|---|
| `employee.list_employees` | 8, **every one inside `employee.py`** — an island | linked: nav **and** card |
| `auth.access_log` | **ZERO, anywhere in the application** | linked from `/users` — see below |
| `receipt.list_receipts` | 7, from `client.py` and `ra.py` | linked: card. The only top-level register with none |

⚠ **`/access-log` is deliberately NOT on the launcher.** That strip is for
registers somebody works in; the refusal log is a **diagnostic, not an audit
trail** — ABOUT.md §7 gap 23, an in-memory `deque(maxlen=500)` that dies with
the process — and putting it on the landing page would advertise it as more
than it is. Its parent is `/users`, which is where you go when somebody says
they were refused something.

**What replaces the deleted test** is a sweep over `app.url_map`:
`test_every_classified_page_is_reachable_from_the_nav_or_the_launcher` requires
every classified landing page to be a nav entry, a card, a form its own register
offers, or a **named exception with its reason written beside it**. Verified
non-vacuous: remove any one of the three links and it names it. A page added in
a later pass is covered the day it is registered.

⚠ **The nav/golden coupling is NOT closed by this and must not be read as
closed.** It is ABOUT.md §7's first gap, it cost five documents +248 bytes each
here, and it will cost the same five again on the next nav change. The fix is
the delivery challan's shape — a document route with no nav at all, which is why
the challan alone did not move — and re-baselining is not the fix.

⚠ **It cost the same five again on 29 August 2026, fifth pass** — **+342 bytes
each**, for the measurement register's nav entry — exactly as predicted, one
pass later. Two nav entries, ten re-baselines, two passes. The prediction was
right and the fix is still unbuilt.

**L. The pre-measurement RA bills — a SECOND grandfathered set, and it is
pinned. 29 August 2026, fifth pass.** *New.*

`created_by` was the first. This is the second and its shape is identical: a
rule arrived after the records it governs, and neither obvious answer is
acceptable — refusing every existing installation bill strands live records,
allowing them silently pretends the rule held when it did not.

**Measured on the live database: ONE bill.** Seven RA bills exist, one is on the
installation leg, and it claims a quantity with no measurement behind it —
`SF/RA/26-27/0006`, RA1 on project *Work2*, quantity 1.
`tools/backfill_measurement_pin.py --write` marked it `pre_measurement = True`
and wrote `{"at": …, "count": 1, "ids": [...]}` to
`STORE["settings"]["measurement_migration"]`.

- The bill **keeps its typed quantity** — nothing recomputed, no figure moved.
- It renders a **"Typed quantity"** marker **on screen only**. Never on paper: a
  note on an issued claim saying its figures were typed is exactly the sentence
  nobody wants read by a main contractor, and a test renders the printed sheet
  and asserts every spelling of it is absent.
- Its project keeps the **BOQ ceiling** in `ra.overclaims()`, so the chain is
  not stranded — and a test asserts the ceiling **moves** the moment an approved
  sheet lands, so the exception does not become a permanent exemption.
- The mark is **never inferred** from a missing measurement. Inferring it is how
  the set would grow.

⚠ **`tests/test_measurement_pin.py` is the point of the whole rule**, and it
carries its own vacuity check: the sweep passes on a fresh database because it
finds nothing, so a **second** test plants exactly the record that must be
caught and asserts the same walk catches it. That is the defect pass D found in
two of its own tests, closed here by construction rather than by intention.

✅ ~~**M. `/measurement/` is UNREACHABLE on the live database until an Owner
acts, and that is a deliberate hand-off rather than an omission. 29 August
2026.**~~ **RESOLVED 30 August 2026 (pass F) — and it was worse than this entry
knew.** *Kept in full below, because the reasoning is right and only the
disposition changed.*

The hand-off was never taken up. On 30 August the live database was measured and
held **fourteen** permissions that reached **no role at all** — not six. The
other eight are `employee.*` (**C4**) and `attendance.*` (**C5**), minted on
29 August and unreachable ever since, so **C4 and C5 stood on the board as BUILT
while nobody, the Owner included, could open either page.**

All fourteen are now granted — **46 grants across 6 roles** — authorised in
advance by the **30 August 2026 override block**, which was written and
committed **before** the mutation rather than acknowledging it afterwards. That
is the discipline the fifth block asked for, and it is the whole reason this
entry could be closed rather than repeated.

⚠ **The class is closed, not the instance.** The repair is now general —
`auth.role_permission_drift()`, `auth.orphan_permissions()` and
`auth.apply_drift()`, driven by `tools/reconcile_role_permissions.py`, a dry run
by default that prints the entire proposal before it writes — instead of a
fourth copy of the same twenty lines pasted into a migration written for
something else. `tests/test_permission_reachability.py` is the guard, and its
docstring records that **the obvious form of that test cannot fail**, because
the Owner role is `list(_ALL_PERMS)` and holds every permission by
construction. See ABOUT.md §2g.

The original entry, unchanged:


`auth.ensure_builtin_roles()` never rewrites an existing role's permission list
— once an Owner has edited what Director means, a restart must not undo it — so
the six new `measurement.*` permissions exist in `auth.BUILTIN_ROLES` and on a
fresh database, and **not** on the role records the live database already holds.
Nobody there holds `measurement.view`, so `auth._gate()` refuses the whole
module, **including for an Owner**: there is no Owner bypass in the gate.

The previous migration solved the identical problem by silently rewriting four
live role records. That was disclosed by pass D and is acknowledged
retrospectively in the fifth override block, **which says the next migration
touching identity data must be authorised on its own terms.** So this one does
not take that decision: `--grant-roles` exists, prints exactly what it would
write, is **off by default**, and **was not run**.

**One command closes it**, and it is the client-facing owner's to type:

```
python tools/backup_db.py --label pre-measurement-grants
python tools/backfill_measurement_pin.py --write --grant-roles
```

or, with no code at all, four to six ticks per role at `/roles/edit/<id>` —
Owner, Director and Operation Head take all six; Sales Manager and Accountant
take `measurement.view` and `measurement.print`. Purchase Manager and HR take
none, by our reversible default and by B4's wall respectively.

---

## 7. Legend

- **BUILT** — code exists **and** tests cover it. Nothing was upgraded to BUILT on the basis of having been opened in a browser.
- **PARTIAL** — some of it exists; the "What is left" column names precisely what does not.
- **NOT STARTED** — no code. Written in preference to guessing wherever evidence was absent.
- **BLOCKED** — cannot be built until a named decision is taken by a named owner. §5 carries both.

The **Browser?** column is ticked by hand after someone has actually opened the
page. It is never filled in by a generated pass.
