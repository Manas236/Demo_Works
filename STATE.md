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

**As of:** branch `antigravity-dev`, 30 August 2026 (**seventh pass** — **B8
authorised and NOT built**; the board does not move and stands at **17 of 20**).

⚠ **Two passes have run since this line last named the current one**, which is
this file's own predicted failure mode:

- **Sixth pass, 30 August 2026 — a cleanup pass.** No Phase 3 item; three
  defects and three recurring failures closed with guards. It reconciled
  **14 permissions held by no role at all**, which is why C4, C5 and C2 were
  reachable by nobody — including the Owner — until it ran.
- **Seventh pass, 30 August 2026 — B8.** **Authorised** by the owner (BLOBs in
  their own table) and then **not built**: `db.py` persists by
  snapshot-and-diff and cannot carry a binary side table
  ([ABOUT.md §4](ABOUT.md)). The pass stopped there rather than invent a second
  persistence mechanism while he was away. What it did deliver is a
  **field-level** escaping guard — the collection-level one added by the sixth
  pass cannot see a single dead field, which is the exact shape of the bug pass
  E shipped.

*(The line this replaces described the fifth pass — **C2** and **C1** built, the
board 15 → 17, 3C 2/6 → 4/6, B7's print gate narrowed by two named exceptions,
and a second grandfathered set pinned at one live RA bill. It is summarised here
rather than deleted because it stood through two passes that made it stale.)*
**Tests:** **1,683 passed / 2 skipped** in the openpyxl **absent**, both client workbooks **absent**, global `C:\Program Files\Python310` (CPython 3.10.11), **no `.venv`**
configuration — measured on 30 August 2026 by running the suite in it. ⚠ *(It
read **1,367 / 1** here until this edition, which was the 28 August figure: the
two 29 August passes before this one added 20 and 92 tests and neither updated
this line. The second skip is new and is not openpyxl's — see ABOUT.md's table.)*
*(It read
1,225 / 1 before §1.18 added 50 tests closing Phase 3A
([tests/test_po_charges.py](tests/test_po_charges.py) 25,
[tests/test_ra_edit_delete.py](tests/test_ra_edit_delete.py) 11, plus 11 more in
[tests/test_po_rate_edit.py](tests/test_po_rate_edit.py) and 3 in
[tests/test_receipt_write_off.py](tests/test_receipt_write_off.py)),
1,151 / 1 before §1.17 added 74 tests over the Phase 3A document items
([tests/test_po_discount.py](tests/test_po_discount.py) 22,
[tests/test_po_rate_edit.py](tests/test_po_rate_edit.py) 21,
[tests/test_receipt_write_off.py](tests/test_receipt_write_off.py) 21,
[tests/test_client_outstanding.py](tests/test_client_outstanding.py) 10),
1,102 / 1 before §1.16 added 49 tests over permission-filtered navigation
([tests/test_nav_visibility.py](tests/test_nav_visibility.py)),
1,079 / 1 before §1.15 added 23 over the sign-out chip
([tests/test_nav_user_chip.py](tests/test_nav_user_chip.py)), 1,062 / 1 before
§1.14 added 17 over the privilege-escalation attack
([tests/test_privilege_escalation.py](tests/test_privilege_escalation.py)), and
1,058 / 1 before §1.13 added 4 over
[tools/set_password.py](tools/set_password.py); each figure was re-measured at
the start of the pass that moved it rather than quoted, and each matched.
986 / 1 from 26 August, 923 / 1 from 23 August, and 838 / 1 from 16 August. The
986 figure was re-measured at the start of the 27 August pass rather than
quoted, and matched. The +72 is the escaping pass and the adversarial
verification of Phase 3B — see §1.12: `tests/test_escaping.py` (31),
`tests/test_access_control_adversarial.py` (29) and
`tests/test_access_matrix_doc.py` (12).)*

**A second configuration is now measured rather than derived:** the repo's
`.venv` (CPython 3.10.11, **openpyxl 3.1.5 present**, both workbooks absent)
reports **1,684 passed / 4 skipped** against the same commit, and read
**1,465 / 4** before this pass's 67,
**1,388 / 3** before the third 29 August pass's 78,
**1,276 / 3** before the 29 August pass's 92 tests,
**1,226 / 3** before §1.18's 50 tests,
**1,152 / 3** before §1.17's 74 tests,
**1,103 / 3** before §1.16's 49 tests, **1,080 / 3** before §1.15's 23,
**1,063 / 3** before §1.14's 17,
**1,059 / 3** before §1.13's 4 and
**987 / 3** against the pre-escaping code. Every one of those was measured, not derived. The **third** configuration — openpyxl present *with*
the client workbooks — is **still derived**, because neither workbook is on this
box; [ABOUT.md §1](ABOUT.md) marks that row as such rather than silently
updating it.

A count quoted without its configuration is not a count, and a count nobody ran
is a claim. That table also explains why the two mechanisms produce
different-looking numbers — a module-level `importorskip` reports **one** skip
however many tests sit behind it, which is exactly the +1 pass / +2 skips
between the two measured rows above.
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
Both are new scope and **chargeable** there. **Item 4 was not named in the 15
August override block**; the **16 August 2026 block** is a fresh dated
authorisation that covers it and names the one-day gap. The 15 August block was
not amended.

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

### 1.8 The delivery challan, and one shared line picker · ✅ 16 August 2026

⚠ **Item 5 was built under the §0 override in
[CLIENT_CHANGES.md](CLIENT_CHANGES.md)**, with MG/SF/2026-02 still unsigned.
New scope, **chargeable** there. **The same 16 August block also carries the
fresh dated authorisation for item 4**, built one day earlier with none of its
own; the 15 August block was left byte-intact.

- **`boqpick.py` — the shared BOQ line picker**, extracted from `po_draft.py`
  at its **second** consumer rather than its fourth. A **leaf**: it imports
  `boq` and `pipeline`, renders no document, owns no route, and knows nothing
  about either consumer. `/po/create` was pinned byte-for-byte **before** the
  move and is byte-identical across it, as are the four printed sheets.
  [ABOUT.md §2e](ABOUT.md). `ra.py`'s claim grid was deliberately left alone —
  it carries the over-claim guard and money columns.
- **`challan.py` — `/dc/`** (CLIENT_CHANGES.md item 5). Built to their own
  DC54: title band inside the page frame and above the letterhead, two
  two-column blocks, a **DESCRIPTION OF GOODS** band, and a four-column table.
  **No rate, no amount, no tax, no total, no bank block, no rupee sign.**
- **Beside the RA bill, not below it.** `challan.py` may not import `ra.py`: a
  challan records goods moved and an RA bill records money claimed, and they
  legitimately disagree. ⚠ **Nothing reconciles them** —
  [ABOUT.md §7](ABOUT.md) gap 19, taken on deliberately.
- **The consignee is the SITE**, defaulting to us, never wired to the BOQ's
  billed-to party. Free-text fields with the address book as an optional
  prefill.
- **Numbering is a global high-water mark with a blank default prefix**, so it
  can be seeded to 55 and continue their bare-integer challan book. A deleted
  challan spends its number.
- **Over-dispatch warns and never blocks** — the opposite call from the RA
  over-claim guard, and `BLOCK_OVER_DISPATCH = False` is where the decision
  lives. Cumulative dispatch is derived across the revision chain, never
  stored.
- **Two `docsheet` seams** — `sheet_open(title_band=)` and
  `sig_block(left_html=)` — both default to `None` and emit the bytes they
  always did. [ABOUT.md §2d](ABOUT.md).
- [tests/test_challan.py](tests/test_challan.py) — 46 tests. The print golden
  now asserts the challan's letterhead is **byte-identical** to the tax
  invoice's, which is the fifth document to carry that assertion.
- ⚠ **Whether their challan particulars satisfy Rule 55 of the CGST Rules, and
  whether an e-way bill obligation attaches, are questions for their CA** —
  [ABOUT.md §7](ABOUT.md) gap 20, CLIENT_CHANGES.md §3 question 2b. **Do not
  encode a guess.**

---

### 1.9 Employee & Miscellaneous Charges ledger — CLIENT_CHANGES.md item 9 · ✅ 16 August 2026

- `STORE["charges"]` — its own collection in `db.COLLECTIONS`.
- `charge.py` — the ledger and the add/edit/delete pages. A **leaf**: it imports nothing that renders a document.
- `gross_amount` is derived dynamically for display.
- Charge heads are editable via `/settings`.
- Optional association with a project.

---

### 1.10 Project Structure (Pass A) · ✅ 16 August 2026

*(Numbered **1.7** and sitting below §2.2 until 23 August 2026 — a second §1.7
under a rule that had already closed §2, so §1 appeared to end at 1.9 and this
section was invisible to anyone reading §1 in order. Renumbered to **1.10**, the
next free number after §1.9, and moved into sequence. Content unchanged. The
other §1.7 — client segregation, the draft PO and the shared printed sheet —
keeps its number, and §3.3's `(§1.7)` reference points at that one and is
correct as it stands.)*

The project structural foundations have been built.
- **Projects** are now top-level commercial engagements that group BOQs, Proformas, and Purchase Orders.
- `project.py` handles the creation and editing of project metadata.
- `projectview.py` provides the Project Detail Page, strictly enforcing the "no money" rule (no profit/loss logic).
- BOQ revisions are handled correctly: attaching a BOQ to a project seamlessly attaches its entire revision chain.

### 1.11 Phase 3B — authentication, roles and access control · ✅ 26 August 2026

**The application is closed.** Until this landed there was no user, no session,
no role and no permission anywhere in it, and every route was reachable by
anyone who could reach the port.

⚠ **This is Phase 3, not Phase 4, and it was gated.** It was built under the
dated **26 August 2026 OVERRIDE** block in [CLIENT_CHANGES.md](CLIENT_CHANGES.md)
§0, with **MG/SF/2026-02 still unsigned** and expiring 28 August 2026. It covers
**B1–B5 only**. B6, B7, B8 and the whole of 3A and 3C are **still gated** — read
that block before touching any of them.

What shipped, in [auth.py](auth.py) (1,639 lines, a new module):

- **B1** — user accounts, login, logout, first-run `/setup`, `/account`, and a
  non-interactive [tools/seed_users.py](tools/seed_users.py). Passwords are
  `werkzeug.security` hashes. Users are **deactivated, never deleted**.
- **B2** — **79** permissions minted in code (61 when this line was written), roles as editable data, effective
  permissions the **union** of a user's roles. A role edit lands on the user's
  next click, not their next login.
- **B3** — the Owner / Admin split, modelled as "Owner is whoever holds
  `admin.roles`". Two guards stop a lockout: a non-Owner cannot grant the Owner
  role, and the last active Owner cannot be deactivated or edited out of it.
- **B4** — seven builtin roles (B4's six plus Owner), seeded idempotently.
- **B5** — default deny, as one central registry and one `before_request` hook.
  **An endpoint absent from the registry is refused**, so a route added later
  fails closed.

Also closed here: **[ABOUT.md §7](ABOUT.md) gap 8**, the `SECRET_KEY` demo
default. It stopped being untidy and became session forgery the moment sessions
went live.

**Four new gaps opened**, all in [ABOUT.md §7](ABOUT.md): **21** no documented
password-reset path for a locked-out last Owner — *which this pass then walked
straight into; closed 27 August 2026, §1.13* — **22** no rate limiting or
lockout on `/login`, **23** the refusal log is a diagnostic and not an audit
trail, **24** permissions are endpoint-level only — which is the one the B6
approvals ladder inherits, because *"a user cannot approve a record they
created"* cannot be expressed in the registry.

~~**Still open from CLIENT_CHANGES-2.md's own "Security items promoted by this
phase":** the unescaped output in `product.py` and `quotation.py`.~~ ✅ **Closed
on 27 August 2026 — see §1.12**, which also found that the defect reached far
wider than those two files. Role-based access makes an authenticated insider the
threat model, and a stored XSS there lets one user hijack another's session —
which, with an approvals ladder, means approving their own submissions. It was a
blocker for B6, not for B1–B5, and it no longer blocks B6.

⚠ **This section is the record of what the 26 August pass shipped and is left
exactly as it was written.** What it claimed was verified independently on
27 August 2026 and **nine of eleven attacks came back clean**; the two that did
not are named in §1.12 and are fixed. Read the two together — this one says what
was built, §1.12 says what happened when somebody tried to break it.

Per-item evidence with `file:line` and test names is in
[PROGRESS.md](PROGRESS.md) §4.

### 1.12 Escaping, and Phase 3B verified by attack · ✅ 27 August 2026

**Two jobs, neither of them new features.** One closed the last security item
CLIENT_CHANGES-2.md promoted; the other went looking for holes in the access
layer §1.11 shipped, because nobody had.

⚠ **Not gated, and no new override block.** [CLIENT_CHANGES.md](CLIENT_CHANGES.md)
§0's standing exemption covers **defect and reachability fixes against scope
already sold under MG/SF/2026-01**, and CLIENT_CHANGES-2.md names the escaping
work as a *narrow security fix* the `product.py` / `quotation.py` freeze
explicitly permits (precedent `9d060ee`). The 26 August block already treated
the other item in that same sentence — the `SECRET_KEY` default — as exactly
that. Verifying and documenting work that is already built is not new scope
either. **Nothing gated was started:** B6, B7, B8 and the whole of 3A and 3C are
untouched.

#### What was built — the escaping half

User text now reaches HTML escaped, everywhere it reaches HTML. CLIENT_CHANGES-2.md
pointed at two files; enumerating it properly — a payload written into every
free-text field, then all 83 pages fetched and the bytes read — found **eight
classes across seventeen files**. In plain terms:

- Anything a person typed into a record — a customer name, a product
  description, a specification clause — could contain instructions for the
  browser instead of text, and the browser obeyed them.
- **A link was enough.** Two of the eight needed no stored record at all: a
  crafted URL handed to a signed-in user ran code in their session on nine
  different list pages.
- **The company's own identity was one of the sinks.** Everything typed at
  `/settings` — the legal name, the address, the GSTIN, the bank block — printed
  on the letterhead of every document raw. That one is outside both files the
  specification named, and it is the worst-placed of the lot, because it is on
  *every* document rather than one record's own page.
- Worst of all, two pages executed `{{ … }}` typed into a record, and a product
  named `{{ config['SECRET_KEY'] }}` **printed the application's signing key**.
  Anybody who could add a product could then forge a login cookie for any
  account, which would have made the whole of §1.11 decorative.

**How it works:** every value is passed through one escaper on its way into the
page, so `<` becomes `&lt;` and the browser draws it as text instead of obeying
it. The characters are *converted, never removed* — a customer really called
`Smith & Sons <Bombay>` still prints as their own name, per
[INTRODUCTION.md §9](INTRODUCTION.md). The two pages that re-parsed their own
output stopped doing so.

**Five printed documents moved by 8 bytes each.** Only the letterhead and the
footer; every other block is byte-identical. The whole difference is the `&` in
*"Fire Protection Systems & Services"* now being written `&amp;` — which a
browser draws as the same `&`. **No rendered figure changed.** The arithmetic is
written out in `tests/test_print_golden.py`.

#### What was built — the verification half

Eleven attacks on the access layer. **Nine were clean.** Forged and unsigned
session cookies are refused; deactivating somebody takes effect on their very
next click rather than their next login; a role edit lands immediately; the
seven roles get exactly the administration access they should, hit directly by
URL rather than through the menus; every lockout guard refuses a direct POST;
`/setup` refuses to mint a second Owner; no error page renders before the gate;
a route added with no permission declared is refused even to an Owner; and the
refusal log records who was refused and what they wanted **without** recording
passwords, cookies or form contents.

**Two were not.**

1. **A read permission authorised a write.** `/projects/view/<id>` is a view
   page, and was classified as one — but posting to it re-attaches a schedule to
   a project. Sales Manager, Purchase Manager and Accountant are all refused the
   project *edit* page and could all make that change through the *view* page.
   Fixed with a check on the write path only.
2. **The login page leaked which usernames exist.** The wording was careful and
   identical for both failures; the *timing* was not. A real username took 70 ms
   to reject and an unknown one took 0.3 ms, because only the real one did the
   password-hashing work. **239×** — visible in a browser, on the first try, no
   statistics needed. Fixed by doing the same work either way; now 1.0×.

#### What was deliberately NOT built

- **No rate limiting or lockout on `/login`.** Still open ([ABOUT.md §7](ABOUT.md)
  gap 22) and still needs a decision, because locking an account under attack is
  also a way to lock out the last Owner. Closing the timing leak narrows the
  attack; it does not stop password guessing.
- **The route registry was not re-keyed per method.** 44 pages answer both
  reading and writing under one permission; for 43 of them that is correct and
  is *stricter* than splitting them. The one exception got a guard. The general
  shape is recorded as gap 24b rather than fixed wholesale, because splitting
  the rest draws a read/write line that is the client's call.
- **Nothing in `product.py` or `quotation.py` was tidied, renamed or
  restructured.** Values were escaped and nothing else. Those files remain
  frozen against refactor.
- **The two dead permissions and the object-level question are untouched.**
  Nothing here restricts anybody to their own projects or their own documents;
  that is gap 24 and it is B6's problem.

#### What is not trustworthy yet

- **The role grid is still ours, not the client's.** Seven roles × **79**
  permissions is **553** cells and **52** of them come from the specification.
  (It read *"× 61 … is 427 decisions and 16"* until 30 August 2026; the
  document's own generated header is the figure to trust.)
  [docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md) now marks every single cell as
  specification or derivation, and it exists to be walked through with the
  client rather than filed.
- **The refusal log is still a diagnostic, not an audit trail** (gap 23). It is
  in memory, it holds 500 entries, and a restart empties it. It records
  refusals only — nothing anywhere records successful access.
- **Escaping is now swept by test on every route, but only for the routes that
  exist.** The sweep reads `app.url_map`, so a new page is covered the day it is
  registered; a new *rendering helper* used by an existing page is not
  automatically covered.
- **The timing test is a timing test.** It allows an 8× spread against a defect
  that measured 239×, and it exists to catch the fix being deleted — not to
  certify constant-time behaviour, which Python cannot give.

New: [docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md), generated by
[tools/dump_access_matrix.py](tools/dump_access_matrix.py) and never hand-edited.
Three gaps closed in [ABOUT.md §7](ABOUT.md) — **7**, **9d** and **9e** — and two
opened: **24b** and **25**.

---

### 1.13 Locked out of our own install — break-glass recovery · ✅ 27 August 2026

**The gap that had already happened.** §1.11 closed the application and seeded a
single Owner (`manas`), signed in as it during testing, and recorded the password
nowhere. The install was left with **an active Owner nobody could sign in as** —
which is [ABOUT.md §7 gap 21](ABOUT.md) exactly as written, no longer
hypothetical. Diagnosed rather than assumed: the app's own `db.CONFIG` was
imported and queried, confirming **one** user, active, holding `admin.roles`,
created 26 Aug 2026 10:54, in `samruddhi_qms@127.0.0.1:3306` — the same database
`tools/seed_users.py` writes to, because both import the same `db` module object.
Not a config split; simply an unknown password.

⚠ **Not gated, and no new override block.** This is a local developer tool and a
recovery action on our own install, not client scope: nothing in
[CLIENT_CHANGES.md](CLIENT_CHANGES.md) or CLIENT_CHANGES-2.md is advanced by it,
no route was added, no permission or role changed, and
[docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md) is byte-identical because there
was nothing in it to move. **Nothing gated was started.**

#### What was built

**[tools/set_password.py](tools/set_password.py)** — non-interactive
`--username X --password Y`. It **sets** passwords and **does not create users**:
an unknown username is refused, listing the accounts that do exist, because a
typo that mints an account is worse than a typo that fails. It owns no policy of
its own — the hashing is imported from `auth`, where `/login` reads it, and the
placeholder/length rules from `seed_users._reject_password` — so neither can
drift from the check that has to accept the result. It refuses to run when
`db.init()` is false, verifies the new hash with `check_password_hash()` before
writing, and **never prints the hash**.

**A second Owner, which is the mitigation the tool is not.** A break-glass CLI
needs a terminal on the box; two Owners need only a browser. `recovery` was
created with `tools/seed_users.py --roles owner,director`. The install now holds
**two active accounts with `admin.roles`**, and either can reset the other at
`/users/edit/<id>`.

#### Verified by driving the real server, not by asserting it

The app was started on `127.0.0.1:5057` against the live MySQL and walked over
HTTP: **33 of 33 checks passed.** Both accounts signed in through the real
`/login` and reached `/`, `/users`, `/roles`, `/boq/view/<id>` and
`/boq/print/<id>` and `/account`; `/account` changed each account's own password,
the new password signed in, the old one stopped working, and each was rotated
back so the recorded password is the live one. Anonymous requests to all six
still redirect to `/login`, `/setup` is closed now that users exist, and both a
wrong password and an unknown username are still refused with the same message.

**The login path was not touched.** No flag, no bypass, no backdoor — the fix is
a tool that writes a hash `/login` already knows how to read. `auth.py` is
unchanged by this pass.

**+4 tests**, all in [tests/test_auth.py](tests/test_auth.py). The tool's
*behaviour* needs a live MySQL and cannot run in the suite — it refuses outright
when `db.init()` is false, which is the point of it. What the four hold is the
half that can rot in silence: that it shares `seed_users._reject_password`
rather than owning a second copy of the policy, that it reaches hashing through
`auth` and never imports `werkzeug.security` itself, that it calls neither
`create_user()` nor `ensure_builtin_roles()`, and that no `print()` in it
carries a hash. All four are read from the **AST**, because the docstring says
several of these things in prose and a text search would pass on the words
alone. Each predicate was checked against a file that *should* trip it —
`auth.py` trips the werkzeug rule, `tools/seed_users.py` trips the
`create_user` rule — so they discriminate rather than merely pass.

**Five print goldens byte-identical**, asserted not assumed: no golden file is
modified in the working tree and `tests/test_print_golden.py` passes unchanged.
`docs/ACCESS_MATRIX.md` is likewise untouched and needed no regeneration — no
permission, role or route classification moved.

#### What this does not close

`/account` still tells a locked-out user only that "an Owner sets a new password
for you", and **nothing client-facing documents either recovery path** — the
client-facing half of gap 21 is still owed. The missing rate limit (**gap 22**,
narrowed but not closed by gap 25) is untouched, and e-mail reset stays out of
scope per CLIENT_CHANGES-2.md B3.

One gap closed in [ABOUT.md §7](ABOUT.md): **21**. None opened. Rows 2 and 3 of
ABOUT.md §1's test table were **re-measured and corrected** — they still read the
26 August figures, because §1.12 updated this file, PROGRESS.md and
INTRODUCTION.md but not that table.

---

### 1.14 A Director was one password field away from Owner · ✅ 27 August 2026

**Found by attacking the page rather than reading about it.**
[docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md) tells the client a Director
"cannot grant anybody the Owner role, or create a new Owner account". Both
halves were true and both were already tested. **Nobody had tested the third
field on the same form.**

`/users/edit/<id>` is classified `admin.users` and sets a password for any
account it can load. A Director-only account — not the Owner+Director `/setup`
mints — POSTed a new password onto the **Owner's** row, changed no role at all,
signed in as the Owner through the real `/login`, and loaded `/roles` with a
**200**. That is [ABOUT.md §7 gap 24b](ABOUT.md)'s shape for the second time:
the page was classified, one write path on it was guarded, the write path
beside it was not.

Four more attacks got through, all the same sentence: the form took the Owner
role **off** a spare Owner; `/users/deactivate` switched a spare Owner off and
`/users/activate` switched a dormant one back on — which walks the install down
to the single Owner whose password the first attack then sets; and a **limited
admin role** (`admin.users` and little else, exactly the role B2 invites an
Owner to build) conferred four `charge.*` permissions by handing out the HR
role. `_may_grant()` tested one permission — `admin.roles` — and was correct
only because that is the single permission a Director happens to lack.

Five of the ten attacks were already clean, including all three the prompt for
this pass expected to fail: a Director cannot create an Owner, cannot add the
Owner role to anybody, and cannot add it to themselves. `_may_grant()` covered
those on 26 August and `test_an_admin_cannot_promote_themselves_to_owner`
already held them.

#### What was built

The rule is now stated once and enforced in both directions: **a permission you
do not hold, you cannot confer; an account holding a permission you do not
hold, you cannot take over.** `_may_grant()` [auth.py:1181](auth.py#L1181)
widened from one permission to the whole set; `_may_administer()`
[auth.py:1227](auth.py#L1227) is its mirror; `_administer_refusal()`
[auth.py:1272](auth.py#L1272) turns it into the app's ordinary 403 page and
**logs it to `REFUSAL_LOG`**, so it reaches `/access-log` instead of living
only in the attacker's browser. Guards `/users/edit`, `/users/deactivate` and
`/users/activate`, on **GET as well as POST**.

Two exemptions, both load-bearing: an **Owner** short-circuits (the tier can
already grant itself anything by editing a role), and **acting on your own
account is always allowed** (you gain nothing you already hold, and
`_would_strand_install()` still guards the one self-inflicted lockout).

📌 **A judgement call, recorded as one.** A Director can no longer administer an
Owner account *at all*. B3 says an Admin may "deactivate users" and does not
except Owners, so this is a tightening past the letter of the specification. It
is right because `_would_strand_install()` only protects the **last** Owner: a
Director could switch spares off one at a time and then reset the survivor. It
costs this install nothing — §1.13 gave it two Owners, and an Owner administers
an Owner.

**+17 tests**, all in
[tests/test_privilege_escalation.py](tests/test_privilege_escalation.py).
**Seven of them fail against the code as it stood** — verified by running the
file against `HEAD:auth.py` and restoring, not by assuming it. Every attack is
paired with a control on the same route and the same field, so a Director
locked out of `/users` entirely would fail this file rather than pass it.

**No golden moved** — this pass touched no chrome. `docs/ACCESS_MATRIX.md` was
regenerated: the **grid is unchanged** (no permission, role or route
classification moved) and the two lines that changed are the Director's prose,
which now says they cannot touch an Owner's account.

No gap closed outright in [ABOUT.md §7](ABOUT.md); **26 opened and closed in the
same pass**, which is how a hole found and fixed together is recorded here.

---

### 1.15 A way to sign out, built around the golden coupling · ✅ 27 August 2026

**The application had no sign-out control.** `/logout` shipped with §1.11 on 26
August, works, and confirms on GET before destroying on POST — and **nothing in
the interface linked to it**. The only way out of a session was to clear a
cookie or wait twelve hours.

The reason it had been left out is recorded in [ABOUT.md §5](ABOUT.md): the
print goldens hash whole responses, printed documents render `_nav()`, so a nav
change moves them. §1.11 was told not to touch `_nav()` and did not.

#### The coupling, measured before anything was changed

`_nav()` was replaced with a sentinel and
[tests/test_print_golden.py](tests/test_print_golden.py) re-run. **Five of its
eleven assertions moved:** the tax invoice, the proforma, the purchase order,
the RA bill and the BOQ line picker at `/po/create`. The **delivery challan did
not** — `challan.print_dc` renders no nav at all, which is the shape all six
document routes should have. So the coupling is real, it is narrower than "every
printed document", and one document already proves it is avoidable.

#### Built around it, not through it

**Styles**: `dashboard.USER_CHIP_STYLES`, a constant of its own, emitted as a
`<style>` element **in the body beside the chip**. `BASE_STYLES` — the block
those goldens hash — is not touched, and no page's `<head>` had to change.

**Markup**: `dashboard._user_chip()`, called from inside `_nav()`, so the chip
reaches every page in the application **including `/product/` and
`/quotation/`, neither of which was edited**. That is the whole argument for
putting it in `_nav()` rather than at 39 call sites: those two files are frozen.

**Suppression**: the chip's markup is still bytes, so it renders empty on the
six endpoints a golden pins — `dashboard.PINNED_PAGES`. A hand-written set of
routes is exactly the drift Part C refuses to accept, so it is checked against
the golden file itself: `test_the_suppression_set_is_exactly_what_the_goldens_pin`
reads the URLs out of that file's **AST**, resolves them through the live
`url_map`, and fails if the two disagree in either direction.

**The control is a link to `GET /logout`**, not a form. `POST /logout` is still
what destroys the session, and the GET confirmation from `9d060ee` stays — a
form in the nav would have put a `<form>` on every page and skipped it.

📌 **The price, stated rather than hidden.** Six pages carry no sign-out
control, three of them ordinary screen pages (`/invoice/view`,
`/proforma/view`, `/purchase/view`). The fix is to break the nav/golden coupling
by giving those routes challan-shaped shells; it is **not** to re-baseline
anything. Recorded against the "Global Nav vs Print Goldens" bullet in
[ABOUT.md §7](ABOUT.md), which is narrowed by this pass and stays open.
`/extractor/` is untouched — it builds its own dark-canvas `<nav>` and does not
use `_nav()` at all.

**+23 tests** in [tests/test_nav_user_chip.py](tests/test_nav_user_chip.py).
**No golden moved**: `tests/test_print_golden.py` is unmodified and passes, and
that file — not this one — is the evidence.

---

### 1.16 The launcher stops offering doors that refuse · ✅ 27 August 2026

**Every nav entry and all fifteen dashboard cards were shown to everybody.**
Clicking one you had no permission for refused correctly — that half was never
in doubt and is not what changed — but an HR user's landing page listed the
quotation register, the tax invoices, the purchase orders and eleven other
things they cannot open.

#### Derived, never listed

`auth.can_reach(endpoint)` [auth.py:726](auth.py#L726) answers *"would `_gate()`
let this user through?"* from **`ROUTE_PERMISSIONS` — the same dict the gate
answers from.** `dashboard._card()` and `dashboard._nav_links()` ask it, and
each card names the **endpoint** it opens rather than a permission id. Nothing
in `dashboard.py` names a permission in code any more, asserted from the AST by
`test_the_dashboard_names_no_permission_id_anywhere_in_its_code`.

That leaves one function that has to agree with another, so they are made to
answer the same questions: `test_can_reach_agrees_with_the_gate_on_every_endpoint_for_every_role`
sweeps **all seven roles against every classified GET endpoint**, requesting
each URL for real and comparing the result with the prediction. `/setup` is the
one named exclusion and it is not a disagreement — it is PUBLIC and the gate
does let it through; the **view** closes it once users exist.

#### Hiding is presentation. The gate is the gate.

**No permission check was removed, weakened or short-circuited.**
`test_every_hidden_card_is_still_refused_when_hit_directly` hits every hidden
card by URL for each of the seven roles and requires a refusal, and
`test_every_visible_card_actually_opens` is the control — without it a role
locked out of everything would score a clean pass.

#### Empty groups, and the honest empty page

`_module_group()` drops a heading whose cards have all gone — a Sales Manager
sees no "Buy side — money out" block at all, rather than an empty box telling
them there is something they are missing. The zone drops when its last group
does. A role reaching no register at all gets a short explanation naming who
can fix it, instead of a title over a blank page that reads as a failure to
load.

📌 **A judgement call, wider than the brief.** The header's two action buttons
**and the whole pipeline band** are quotation surfaces, so they are suppressed
for anybody without `quotation.view`. The brief said menus and cards; leaving
the band would have left a dozen refusing links on the landing page of an
Operation Head. What that does **not** decide is whether such a user should see
pipeline *figures* at all — recorded as [ABOUT.md §7 gap 27](ABOUT.md), open,
because it is a client question and belongs with the seven-role walkthrough
`docs/ACCESS_MATRIX.md` already asks for.

**+49 tests** in [tests/test_nav_visibility.py](tests/test_nav_visibility.py);
**31 of them fail against the pre-pass code**, verified by reverting
`dashboard.py` and `auth.py` and running them. **No golden moved** —
`NAV_LINK_SEP` exists so the filtered nav renders the byte-identical markup for
a user who may reach every entry, and `tests/test_print_golden.py` is
unmodified and passes.

⚠ **One test-isolation fact worth knowing:** roles are a shared dict that the
`client` fixture does not clear, and `ensure_builtin_roles()` never rewrites an
existing row — both correct, both required by B2. So
`test_auth.py::test_editing_a_role_takes_effect_without_signing_in_again`
leaves `boq.view` on HR for every later test in the run. The new file restores
the builtin permission sets in an autouse fixture rather than the other file
being changed; that test is testing the right thing.

### 1.17 Phase 3A — the document items · ✅ 27 August 2026

**The first pass to build a Phase 3A item.** Authorised by the **27 August 2026
OVERRIDE** block in [CLIENT_CHANGES.md](CLIENT_CHANGES.md) §0, which names
**A1, A2 and A5** and explicitly declines A3. MG/SF/2026-02 was still unsigned
and **expires 28 August 2026**, the day after this work.

Five commits, one per item so a single one can be reverted without losing the
rest: the override block, then A2, A1, A5 and A4.

**A2 — the discount column on the final PO.** A per-line percentage, stored as
`discount_pct`, applied by `purchase._line_total()`.

⚠ **It sits inside the tax base, and that is the whole of the arithmetic.** The
discounted figure lands in the line's `total`, `_totals_of()` sums those into
`subtotal`, and `subtotal` is the only argument `quotation._tax_lines()` sees.
On the test figures: ₹10,000 list less 10% is ₹9,000 taxable, ₹1,620 tax,
₹10,620 — not ₹1,800 and ₹10,800, which is what applying it after tax would
have produced and what nothing but an explicit test would have caught.

The buy sheet got its own `docsheet.BUY_COLUMNS` and its own `.c-disc` rule in
`PURCHASE_STYLES`; `sum_row()` / `total_row()` grew a `blanks` parameter whose
default is byte-identical. **The purchase order golden moved +942 bytes and no
other did** — head +721 of CSS, items +221 of cells, justified line by line in
`tests/test_print_golden.py`.

**A1 — repricing an existing PO.** `GET,POST /purchase/edit/<id>`. The rate was
never locked at creation; what did not exist was a route that changed a
**stored** one. Rates and discounts only — and it is the only way a BOQ-derived
order gets an A2 discount at all, since `_po_lines_from_picked()` writes none.

⚠ **Draft only, and that narrowing is not in CC-2's A1 line.** Recorded PARTIAL
for the same reason A6 is: the code does less than the requirement says, however
good the reason. PROGRESS.md §6-I. Gated by `purchase.create` rather than
`purchase.edit` — §6-J — which moved no cell of the 7×61 grid.

**A5 — the write-off on a payment.** A `write_off` amount beside `amount` on the
receipt, summed by `ra.written_off_against()` and subtracted in
`ra.outstanding_of()` and on the client register.

⚠ **A second field, never folded into `amount`, and that separation IS the
item.** Money that arrived and money the contractor allowed short are two
different facts; folding them was what made the old `mode="adjustment"`
workaround fix Outstanding by breaking Received.

**A4 — verified, not rebuilt.** +10 tests pinning its arithmetic from a second
angle, and the caveat CC-2's A4 note asks for in as many words now renders under
the figures. `test_client_segregation.py` untouched.

#### What was stopped, and why it is the most important line here

**A3 — the additional-charges repeater — was NOT built, and not because of the
commercial gate.** It is stopped on an unanswered **tax** question: a loading or
transportation line on a buy-side PO is either the vendor's own consideration
(s.15(2)(c), inside the taxable value) or a third-party cost outside this
vendor's supply. CC-2 specifies "label + amount", which carries no taxability,
and **no document in this application carries a charge line today** to read the
answer off. Overstating a taxable value overstates the input credit we tell a
vendor to bill. ABOUT.md §7 gap 28, PROGRESS.md §6-H.

**A6 — untouched, deliberately.** Not one line of `ra.py`'s lifecycle moved. The
latest-bill-only restriction on `can_edit()` and `can_delete()` was re-verified
and is still real; lifting it is a commercial question.

#### Measurements

**1,151 → 1,225 passed, 1 skipped** (global `C:\Program Files\Python310`,
no `.venv`, openpyxl absent). **1,152 → 1,226 passed, 3 skipped** (`.venv`,
openpyxl 3.1.5). Both measured at both ends, neither derived. **+74**, in four
new files.

One existing assertion changed: a specification header row's `colspan`, 6 of 8
columns → 7 of 9. Same claim, wider table; old value kept in a comment, and the
row gained two further assertions rather than losing any.

`docs/ACCESS_MATRIX.md` regenerated — **61 permissions and the 7×61 grid
unchanged**, endpoints 85 → 86.

---

### 1.18 Phase 3A — CLOSED · ✅ 28 August 2026

**All six 3A items are BUILT.** Authorised by the **28 August 2026 OVERRIDE**
block in [CLIENT_CHANGES.md](CLIENT_CHANGES.md) §0, which names **A1's
widening, A3 and A6**. MG/SF/2026-02 was still unsigned and **expired on this
date** — this is the last day the decision could be taken against it.

Eight commits, one per item so a single one can be reverted without losing the
rest: the override block, §6-D's arithmetic, A1, A3, A6, the test-leak fix,
docs, and one correcting a counterfactual figure in A3's worked example.

**The shape of the pass is the thing worth keeping.** All three items were
already *possible* on 27 August; each was held by a **question**, not by code,
and the previous edition said so. Two answers were "build it" and one was "the
restriction is correct, keep it". Nobody wrote code to unblock anything.

**A1 — the Draft-only narrowing lifted.** `can_edit_rates()` now refuses only
`Cancelled`. The reason anybody wants an editable base rate is a rate that has
**already gone out**, so Draft-only left exactly that case unsolved — a Draft
rate was never locked, it is a form nobody submitted.

⚠ **The objection is answered rather than discarded.** `update_purchase()`'s
*"changing them behind the document is how a dispute starts"* still holds — and
the dispute starts when the change is **invisible**. Every reprice that moves a
figure writes a `reprice_log` entry: who, when, old rate → new rate per line
that moved, rendered under the order by `_reprice_html()`. Only moved lines are
listed; an unchanged submit writes nothing and says so. The trail is inside
`.po-panel`, which is `display:none` at print — what the vendor holds is the
order, not our record of having changed it. PROGRESS.md §6-I is closed.

**A3 — the item the previous pass was stopped on.** The tax question is
answered: **the charge is inside the taxable value.** The document is a purchase
order we issue to a **named vendor**, so a line on it is that vendor's
consideration — s.15(2)(c), incidental expenses. The third-party reading
describes a cost that would not appear on this vendor's PO at all.

⚠ **The exception is made expressible rather than argued away.** Every line
carries `taxable`, defaulting to true; an untaxed line is added **after** tax.
That is what stops the ruling having to be reopened under time pressure. Where
it enters, in one place, `_totals_of()`:

    subtotal      = sum(line totals)              lines only, meaning unchanged
    taxable_value = subtotal + taxable charges    A3 enters HERE
    tax           = _tax_lines(taxable_value)
    grand_total   = taxable_value + tax + exempt charges

One repeater of four free-text slots, per CC-2's *"do not build four fields"*,
with the client's two named heads seeded into the first two.
⚠ **The `/settings`-editable head list CC-2 also asks for is NOT built** — it
would add a `purchase.py → settings.py` import edge for labels that are already
free text. Recorded as a deviation, not skipped quietly. ABOUT.md §7 gap 28 is
closed; PROGRESS.md §6-H carries the ruling.

**A6 — closed as BUILT WITH A STATED LIMITATION, and not one line of `ra.py`'s
lifecycle logic moved.** The latest-bill-only restriction was put up as a
candidate for lifting and ruled **correct**: RA bills are cumulative, so editing
bill 3 while bill 5 exists corrupts every claim downstream of it. The client
asked without qualification because the chain arithmetic is not his to know.

What changed is the **refusals**. Both stopped one sentence short of useful —
they said no and named the obstacle, and left the operator to guess at the
remedy. Both now explain why cumulative bills matter and name cancelling
forward, newest first, as the supported route. The wording keeps the phrase
`tests/test_ra_routes.py` already pins, so no existing test was retargeted.
Verified **end to end** through `/ra/create` → `/ra/edit` → `/ra/print` and
`/ra/delete`, not against the gate functions. PROGRESS.md §6-A carries the
client-readable wording. **Arbitrary-bill editing is new scope and is priced
nowhere.**

**§6-D's arithmetic — the data decision, taken with the count in front of it.**
The live database was queried before anything changed: **zero adjustment-mode
receipts**, one receipt in total, mode `neft`. So no historical figure moved.
`client.received_val` now excludes adjustment-mode receipts, making **Received**
bank movements only.

⚠ **An adjustment is excluded from Received and is NOT dropped** — it is
subtracted from Outstanding under its own **Adjusted** heading. This is a
**deliberate deviation** from the instruction that authorised the pass, which
would have put every adjustment back into Outstanding: `ra.py`'s own note on
`RECEIPT_MODES` says an adjustment is settled against the bill and *"the money
genuinely stops being outstanding"*, and the §6-D tripwire asserted that
`total_outstanding == 0.0` was **right**. Outstanding is invariant by
construction — `received_val` lost exactly what `adjusted_val` gained.
`ra.outstanding_of()` and `ra.received_against()` were deliberately not changed.

**The test leak, fixed where the mutation is.** `tests/test_nav_visibility.py`
carried an autouse fixture that reset all seven builtin roles before every test,
to undo an edit `tests/test_auth.py` made and never put back. The fixture is
deleted. **Three tests were leaking, not the one that was named** — and the
worst was `test_a_role_cannot_be_given_a_permission_that_does_not_exist`, which
left HR holding a single permission and no `dashboard.view` for the rest of the
run. All three now use one `_role_restored()` guard and each asserts it put the
role back. Verified order-independent both ways round and with the file alone.

#### Measurements

**1,225 → 1,275 passed, 1 skipped** (global `C:\Program Files\Python310`,
no `.venv`, openpyxl absent). **1,226 → 1,276 passed, 3 skipped** (`.venv`,
openpyxl 3.1.5). Both measured at both ends, neither derived. **+50**:
`tests/test_po_charges.py` (25) and `tests/test_ra_edit_delete.py` (11) are new,
`tests/test_po_rate_edit.py` 21 → 32, `tests/test_receipt_write_off.py` 21 → 24.

**Five existing tests were deliberately retargeted and none was deleted.** Four
in `tests/test_po_rate_edit.py` pinned A1's Draft-only narrowing; one in
`tests/test_receipt_write_off.py` was the §6-D tripwire, written to fail when
its defect was fixed. Every one keeps its old assertion verbatim in a comment.

**`/purchase/view`'s golden moved twice, +1,021 (A1) and +937 (A3), both in the
`head` block only.** Every byte is stylesheet or the `Reprice` anchor the Issued
golden order now qualifies for. `items` did not move: the golden carries no
charges and has never been repriced, so **not one printed figure changed**. No
other golden moved.

`docs/ACCESS_MATRIX.md` regenerated and **byte-identical** — no route was added,
so no permission, role or classification moved.

A `mysqldump` was taken before any of it:
`backups/samruddhi_qms-20260828-132711-a1-a3-a6.sql`, 444,047 bytes.

---

---

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

**Dead-Premise Cleanup Checklist — ~~closed 15 August 2026~~ REOPENED 23 August 2026**

⚠ **It was not closed.** One row was ticked against a file that still asserted
the premise; see that row for what was amended on 23 August 2026 and for the two
statements deliberately left standing pending **BQ2**.

The dead premise that "an RA bill is not a tax invoice":

- [x] `ABOUT.md` — Module map description
- [ ] `PHASE4_RA_DESIGN.md` — Design document scope. ⚠ **This was ticked on 15
      August 2026 against a file that still asserted the premise, and it is
      un-ticked here on 23 August 2026 rather than quietly re-ticked.** §5
      carried the `[AMENDED 8 Aug 2026]` note while **§7's decision table,
      directly below it, still answered "Is the RA bill a tax invoice? **No.**
      Claim document only."** Four further statements rested on the same dead
      premise: the §5 bullet header *"Tax — explicitly OUT of scope"*, the ⚠
      instruction ordering ABOUT.md §5 to be corrected **back toward** the dead
      premise, the *"roughly halves the module"* scope-reduction claim, and the
      `❌ Rule 46 full tax invoice engine` prohibition row. **All five were
      amended on 23 August 2026** — struck, not deleted, each carrying the same
      `[AMENDED 8 Aug 2026]` marker and a pointer to §5 so the ruling reads as
      one.

      **It stays un-ticked because two statements were deliberately left
      standing**, and a tick over a live dead-premise assertion is the exact
      error this checklist already made once (see the `ra.py` `_tax_lines` row
      below):

      - **§2** — *"**If the RA bill is the tax invoice** (see §5, this is
        unresolved and it matters), `ref` inherits Rule 46(b): unique within the
        FY and **≤ 16 characters**"*.
      - **§5's prohibition table** — *"❌ FY-unique *statutory* reference |
        `ref` is our document number, **not a tax-invoice serial**; no
        16-character cap"*.

      The second is a dead-premise assertion in plain terms. Both were left
      **because settling them means ruling on whether `ref` is a tax-invoice
      serial**, which is not a documentation pass's call and which the 8 August
      amendment makes arguable in a direction §5 was written before. It is
      raised as **BQ2** in [CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md), where
      BQ1 already depends on the answer. **This row may be ticked when BQ2 is
      answered and those two statements are made to agree — and not before.**
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

- ~~**Delivery challan** — a document type their business uses and this system
  has no equivalent for.~~ ✅ **Built as `challan.py` / `/dc`** on 16 August
  2026 (§1.8), as a BOQ-chain document beside the RA bill rather than below it.
  [DOMAIN.md §5.1](DOMAIN.md). ⚠ Two things it does **not** do: reconcile
  dispatched against claimed quantity ([ABOUT.md §7](ABOUT.md) gap 19), and
  answer whether its particulars satisfy Rule 55 of the CGST Rules (gap 20 —
  **for their CA**).
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

- ~~**`product.py`** — no escaping across ~1,409 lines.~~
- ~~**`quotation.py`** — five sinks, three of which removing
  `render_template_string` does not fix.~~

✅ **Both closed on 27 August 2026 — §1.12.** They were fixed as **narrow
security fixes**, which is the one thing the freeze on these two files has
always permitted (precedent `9d060ee`, and CLIENT_CHANGES-2.md's own "Security
items promoted by this phase" names them as such). Escaping and the removal of
the second template parse; **nothing renamed, restructured or feature-extended**,
and each file carries a header block saying exactly what was and was not
touched.

⚠ **The rest of the prohibition stands, unchanged.** These two files are still
**not to be refactored or feature-extended** — [INTRODUCTION.md §7](INTRODUCTION.md)
is the rule and it is not spent by this. The missing product edit route (ABOUT.md
§7.2) is still not to be built, and `spec.py`'s `_render_form` pattern is still
not to be ported across. What changed is that these two files no longer carry an
unescaped-output defect; what did not change is what you may do in them.

⚠ **And the defect was never confined to them.** The 27 August enumeration
found it in fifteen other files — most importantly the company identity from
`/settings`, which printed raw on every document's letterhead. Treating
"`product.py` and `quotation.py`" as the boundary of an escaping problem is the
specific mistake that pass had to correct; see §1.12 and [ABOUT.md §7.7](ABOUT.md).

### 3.6 Gaps in code that already exists

Owned by **[ABOUT.md §7](ABOUT.md)** and not duplicated here — the missing
product edit route, the inconsistent escaping, the placeholder HSN codes, the
specimen company identity, the absence of a credit-note flow, e-invoicing.

Read it before proposing a fix. What you are about to report is probably
already there, with the reason it has not been done.

---

### 3.7 Documentation drift — known, not yet fixed

**This is the backlog, and it exists so that no further documentation-only pass
is needed.** Every line below is an inconsistency found during the stabilisation
passes of 22–23 August 2026 and deliberately **not** fixed, because fixing it was
outside that pass's scope or is a ruling nobody has taken. **Each one gets fixed
by whoever next touches that file for a real reason** — not by a pass convened to
fix them. If you are editing one of these files anyway, clear its rows and delete
them from here; if you are not, leave them.

Documentation stops being a workstream after this. The next pass writes code.

**Blocked on a ruling — do not clear these opportunistically.** Rows 1 to 4 are
one question, raised as **BQ2** in
[CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md): *is `ref` a tax-invoice serial, and
does it therefore inherit Rule 46(b)'s 16-character cap?* They contradict each
other and cannot be reconciled by editing prose. **Answer BQ2, then fix all four
together** — and un-tick nothing until they agree.

| # | File · line | The drift |
|---|---|---|
| 1 | [PHASE4_RA_DESIGN.md:167](PHASE4_RA_DESIGN.md#L167) | *"`ref` inherits Rule 46(b): unique within the FY and **≤ 16 characters**"*, on a condition the 8 August amendment has since satisfied. **BQ2.** |
| 2 | [PHASE4_RA_DESIGN.md:328](PHASE4_RA_DESIGN.md#L328) | *"`ref` is our document number, **not a tax-invoice serial**; no 16-character cap"* — the same file answering row 1 the other way, and still stating the dead premise. **BQ2.** Also the reason §2.1's cleanup checklist is un-ticked. |
| 3 | [ra.py:216-218](ra.py#L216-L218) | Code comment: *"No 16-character cap. That is Rule 46(b)'s limit on a TAX INVOICE number, and **this document is not one**."* The dead premise, in code. `_REF_CAP = 64`. **BQ2.** |
| 4 | [ra.py:845-846](ra.py#L845-L846) | `next_ref()`'s docstring: *"**No 16-character cap and no statutory meaning**: this is a claim document, not a tax invoice."* Second instance of row 3. **BQ2.** |
| 5 | [INTRODUCTION.md:318-325](INTRODUCTION.md#L318) | §8, *"One rule in this codebase is now known to be wrong"*, still reads *"`ra.py` **currently asserts** … that an RA bill is not a tax invoice"* and *"it is **not yet implemented**"*. It was inverted on 15 August 2026. The whole section is stale and is one of the first things a new reader is told. |
| 6 | [DOMAIN.md:370-376](DOMAIN.md#L370) | §4's opening prose still says *"The code **currently asserts** the opposite"* and cites `test_ra_does_not_pull_in_the_tax_machinery`, a test that no longer exists. Left standing on 23 August 2026 because a requirement's wording is not a status pass's to edit; the correction is the **STATUS — shipped** marker directly below it. |
| 7 | [ABOUT.md:4568-4573](ABOUT.md#L4568) | Gap 15's first paragraph is stale: it says `/ra/print` hardcodes `seller_state = "Punjab (03)"` and a fallback GSTIN. Both literals are gone — [ra.py:3516-3517](ra.py#L3516-L3517) derives the GSTIN from `branding` and the State from the GSTIN's first two digits, and [tests/test_ra_seller_identity.py](tests/test_ra_seller_identity.py) fails if either returns. **The rest of gap 15 is still true and still open**: place of supply with its State code is absent, and the tax head is not derived. Fix the first paragraph only. |
| 8 | [STATE.md:13](STATE.md#L13) | *"**As of:** branch `antigravity-dev`, 16 August 2026"* — this file now carries 23 August 2026 content in §2.1, §1.10 and this section. |
| 9 | [DOMAIN.md](DOMAIN.md) §4.7 · [ra.py:3556](ra.py#L3556) | Not a doc-to-doc drift but a doc-to-code one, recorded because it is easy to misread as a bug: §4.7 says print order is its own concern, and `print_ra()` has no print-order rule at all — it emits stored claim order. **There is nothing to fix and nothing to harmonise.** An agent adding a print order is adding a feature, not correcting a defect. |

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
