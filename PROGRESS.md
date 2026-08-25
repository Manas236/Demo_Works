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
| **Date** | 25 August 2026 |
| **Machine** | home laptop — `c:\Users\manas\OneDrive\Desktop\Demo_Works` |
| **Branch** | `antigravity-dev` |
| **HEAD** | `2ec54f6b297456d4fb703b4a9491611b47c725a0` |
| **vs `origin/antigravity-dev`** | 2 ahead, 0 behind |
| **Dirty files** | 0 — `git status --porcelain` empty. No `.py` file is modified or untracked, so no status in this file depends on uncommitted code. |
| **Test figure** | **not measured this pass.** The pass was constrained to create no file anywhere on this machine other than `PROGRESS.md`; `python -m pytest` writes `.pytest_cache/` and `__pycache__/`, so the suite was not run. No count is quoted from any document either. |

**Item source.** `CLIENT_CHANGES-2.md` only. Count found: **3A ×6 (A1–A6),
3B ×8 (B1–B8), 3C ×6 (C1–C6) = 20.** Matches expectation.

---

## 2. Bars

Only BUILT fills the bar. PARTIAL contributes nothing; BLOCKED contributes
nothing.

```
ALL  █░░░░░░░░░░░░░░░░░░░   1 of 20 BUILT · 3 PARTIAL · 2 BLOCKED · 14 NOT STARTED
3A   ███░░░░░░░░░░░░░░░░░   1 of 6 BUILT · 3 PARTIAL · 0 BLOCKED · 2 NOT STARTED
3B   ░░░░░░░░░░░░░░░░░░░░   0 of 8 BUILT · 0 PARTIAL · 0 BLOCKED · 8 NOT STARTED
3C   ░░░░░░░░░░░░░░░░░░░░   0 of 6 BUILT · 0 PARTIAL · 2 BLOCKED · 4 NOT STARTED
```

---

## 3. What the bars do not say

**The item count does not measure the work.** These twenty items are not
comparable units and the ratio 1/20 is close to meaningless as a measure of
effort remaining. A2 is a column on one form. B5 is a decision applied to every
route in the application, twice.

Three items dominate what is left, and between them they are most of Phase 3:

- **B5 — default deny, two-stage.** Not a feature. It is a decorator on every
  route function in every module, an audit-mode pass, a log to read, a flip to
  enforce, and an AST test asserting no route escaped. It touches more files
  than the rest of 3B combined and it cannot be done incrementally without
  leaving routes silently open.
- **B8 — file attachments.** The first thing that breaks the storage model.
  There is no `/static`, images are base64 data URIs, and `boq.MAX_JSON_BYTES`
  is 300,000 ([boq.py:192](boq.py#L192)) against a photographed supplier bill
  of 2–5 MB. This is new infrastructure — a real file store, a path on the
  record, a size and type gate, and cascade delete — not a field.
- **C3 — merged RA.** Blocked before it starts (§5), and the design pass that
  unblocks it has to settle a statutory numbering question the repo currently
  answers both ways.

B1/B2/B3/B4 are individually smaller but strictly sequential and strictly
prior: none of 3C can be built until a user exists.

---

## 4. Items

### 3A — document and register changes

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **A1** | PO base rate editable | PARTIAL | Editable **at creation**: `RATE_PREFILL_FIELD = "supply_base_rate"` [purchase.py:182](purchase.py#L182); rate box rendered and stored on `GET,POST /purchase/from-boq/<boq_id>` [purchase.py:1662](purchase.py#L1662) and `GET,POST /purchase/from-draft/<draft_id>` [purchase.py:1797](purchase.py#L1797). Test `test_rates_prefill_from_the_supply_base_rate_and_an_edit_is_what_is_stored` [tests/test_boq_to_po.py:240](tests/test_boq_to_po.py#L240). | Editing the rate on an **existing** PO. `POST /purchase/<id>/update` [purchase.py:2030](purchase.py#L2030) is status-and-note only; its docstring states the commercial content of an issued PO is deliberately not editable there. No route anywhere changes a stored PO line rate. | ☐ |
| **A2** | Discount column on final PO | NOT STARTED | The string `discount` does not occur in any application `.py` file. The only repo-wide hit is `.venv/.../rich/_emoji_codes.py`. | All of it: form column, per-line or document-level storage, and the effect on `_totals_of()` [purchase.py:589](purchase.py#L589). | ☐ |
| **A3** | Additional charge lines on final PO | NOT STARTED | No repeater on the PO. No `additional_charge` / `extra_charge` / `loading` / `transportation` field in `purchase.py`. The seed pattern CC-2 points at exists but serves the charges ledger, not the PO: `CHARGE_HEADS_RECORD` [settings.py:353](settings.py#L353), `charge_heads()` [settings.py:361](settings.py#L361). | All of it. Build **one** label+amount repeater seeded from `/settings`, per CC-2's A3 note — not four fields. | ☐ |
| **A4** | Total outstanding on client register | **BUILT** | Computed at [client.py:120](client.py#L120) from `issued_val` [client.py:110](client.py#L110) less `received_val` [client.py:112](client.py#L112); rendered on `GET /clients/` [client.py:219](client.py#L219) at [client.py:280](client.py#L280). Tests `test_outstanding_counts_issued_bills_only` [tests/test_client_segregation.py:151](tests/test_client_segregation.py#L151) and `test_receipts_reduce_outstanding_and_an_overpayment_shows_as_credit` [tests/test_client_segregation.py:173](tests/test_client_segregation.py#L173). | Nothing for A4 itself. **But see §6-D:** CC-2's A4 caveat requires the figure not be presented as authoritative until A5 exists, and the page carries no such caveat. | ☐ |
| **A5** | Write-off / adjustment on a payment | PARTIAL | No write-off field exists on any record. What exists is an adjacent pre-existing capability: receipt mode `"adjustment"` in `RECEIPT_MODES` [ra.py:138](ra.py#L138), offered by `_mode_options()` [receipt.py:326](receipt.py#L326) on `GET,POST /receipts/new` [receipt.py:510](receipt.py#L510). The mode list is covered by `test_the_mode_picker_is_a_select_over_the_shared_list` [tests/test_receipts.py:751](tests/test_receipts.py#L751). | The field itself. Today the only way to clear a short-allowed balance is to file a **second receipt** with `mode="adjustment"` — which does reduce Outstanding, but `received_val` [client.py:112](client.py#L112) sums receipt amounts **without inspecting mode**, so the register's "Received" figure is inflated by every write-off. A5 as specified is a field on the payment, producing no document and no number series. | ☐ |
| **A6** | RA edit and delete — draft only | PARTIAL | All three routes exist and are gated: `GET,POST /ra/cancel/<id>` [ra.py:2740](ra.py#L2740) gated by `can_cancel()` [ra.py:1578](ra.py#L1578); `GET,POST /ra/edit/<id>` [ra.py:3011](ra.py#L3011) gated by `can_edit()` [ra.py:1470](ra.py#L1470); `GET,POST /ra/delete/<id>` [ra.py:3796](ra.py#L3796) gated by `can_delete()` [ra.py:1512](ra.py#L1512). Tests: `test_the_latest_bill_can_be_edited` [tests/test_ra_routes.py:378](tests/test_ra_routes.py#L378), `test_the_latest_bill_can_be_deleted_and_the_number_is_reused` [tests/test_ra_routes.py:748](tests/test_ra_routes.py#L748), `test_a_cancelled_bill_cannot_be_un_cancelled_edited_or_deleted` [tests/test_ra_routes.py:535](tests/test_ra_routes.py#L535). | **The latest-bill-only restriction, verified as real — see §6-A.** A draft that is not the highest `ra_no` on its BOQ is refused **both** edit and delete. CC-2's A6 wording narrows to draft-only and stops there; it does not narrow to latest-only. Whether A6-as-sold covers lifting that is a commercial question, not a code one. | ☐ |

### 3B — users, access and approvals

Nothing in 3B exists. There is no authentication, no user record, no session
identity, no role and no permission anywhere in the application. The one
related fact in code is that `SECRET_KEY` is read from the environment but
still falls back to the demo default:
`app.secret_key = os.getenv("SECRET_KEY", "qms-demo-secret-2024")`
[app.py:53](app.py#L53).

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **B1** | user accounts and login | NOT STARTED | No `users` collection in `store.py`; `db.py`'s collection map [db.py:259](db.py#L259) names no user table. No login route on any blueprint. No password hashing import anywhere — `werkzeug.security` is unreferenced. | All of it, plus the `SECRET_KEY` move CC-2 folds into this item rather than treating as separate — [app.py:53](app.py#L53) still carries the demo fallback. | ☐ |
| **B2** | permissions are named strings, minted in code | NOT STARTED | No permission string, constant or registry in any `.py` file. | All of it: the code-side permission constants, roles as editable data, union of roles for effective permissions, and the `/settings` surface that assigns without allowing new strings to be invented. | ☐ |
| **B3** | Owner / Admin split | NOT STARTED | No user tier concept exists — see B1. | All of it, including the last-Owner-undeletable invariant and the manual Owner-driven password reset. | ☐ |
| **B4** | roles as discussed | NOT STARTED | No role record exists. | Seeding the six roles, the HR restriction from Sales/Purchase/Accounts, and multi-role assignment. | ☐ |
| **B5** | default deny, rolled out in audit mode | NOT STARTED | No decorator on any route function. Route decorators across the app are bare `@<bp>.route(...)` — e.g. [ra.py:2506](ra.py#L2506), [purchase.py:863](purchase.py#L863), [client.py:219](client.py#L219). No AST test over route permissions in `tests/`; `tests/test_import_directions.py` uses the AST technique CC-2 points at, but only for import direction. | All of it, both stages, plus the AST test. Largest single item in Phase 3 — see §3. | ☐ |
| **B6** | approvals | NOT STARTED | No approval state on any record. Every occurrence of "approve/approved" in application code refers to BOQ **approved quantity** — e.g. [challan.py:249](challan.py#L249), [boq.py:2141](boq.py#L2141) — not to an approval ladder. `purchase.py` states the opposite explicitly: *"There is no extra approval step on this path"* [purchase.py:1511](purchase.py#L1511). | All of it, including the load-bearing creator-cannot-approve rule checked against the record's creator. Cannot start before B1. | ☐ |
| **B7** | unapproved documents are view-only | NOT STARTED | Depends on B6, which does not exist. Print routes carry no approval gate: `GET /ra/print/<id>` [ra.py:3370](ra.py#L3370), `GET /dc/print/<id>` [challan.py:965](challan.py#L965). | Gate on the print and download routes, plus the print stylesheet that blanks the view page so `Ctrl+P` does not bypass the gate. | ☐ |
| **B8** | file attachments | NOT STARTED | No `request.files` and no upload handling anywhere in the application. Storage model unchanged: `MAX_JSON_BYTES = 300_000` [boq.py:192](boq.py#L192), no `/static` directory. | All of it: real file storage, path on the record, size and type gate, compulsory on charges, optional on payments, cascade delete with the parent. Call the attached file a **proof of payment**, never a "receipt" — that word is taken by the payment record itself. | ☐ |

### 3C — measurement, labour cost and project result

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **C1** | order of working | NOT STARTED | Neither leg of the stated ordering is wired. `ra.py` contains **no reference to `challan`** at all, so `BoQ → Delivery Challan → RA-Supply` is two unconnected documents rather than a chain; the challan blueprint stands alone at [challan.py:774](challan.py#L774)–[challan.py:1040](challan.py#L1040). `BoQ → Measurement → RA-Installation` has no middle term — no measurement module exists. Installation quantity is still typed straight into the claim grid [ra.py:1315](ra.py#L1315). | Both links. C1 is only closed once a challan constrains supply quantity and C2 supplies installation quantity. | ☐ |
| **C2** | measurement document | NOT STARTED | No measurement module, record, route or test. `db.py`'s collection map [db.py:259](db.py#L259) holds no measurement collection. | All of it: raise from the BOQ, approve, and feed approved quantity into RA-Installation. Depends on B6 for what "approved" means. | ☐ |
| **C3** | merged RA | **BLOCKED** | No merge code exists — `merge` does not occur in any application `.py` file. Blocked on **BQ1 + BQ2** before it can be built at all; see §5. Two live code facts the design pass must start from: `tax_invoice_ref` is a **typed form field**, never minted [ra.py:2899](ra.py#L2899), and when left blank the printed tax-invoice number **silently falls back to the RA `ref`** [ra.py:3486](ra.py#L3486) — the two series are already conflated in code. | The design pass first, then the build. Note CC-2's instruction to put the merge action on the RA register from day one. | ☐ |
| **C4** | employee master | NOT STARTED | No employee record. `charge.py` is titled *"Employee & Miscellaneous Charges Ledger"* [charge.py:2](charge.py#L2) — a charge ledger with a misleading name, **not** an employee master. No employee collection in [db.py:259](db.py#L259). | All of it: employee details and salary. Note the untagged item alongside it — HR's right to **edit** salary is outside C4 and outside MG/SF/2026-02. | ☐ |
| **C5** | attendance and site-wise labour cost | NOT STARTED | No attendance record, route or test anywhere. | All of it: daily presentee/absentee, one employee = one site = one day, and the OT calculation. **The OT multiplier must be a setting, not a constant** — CC-2 is explicit that hardcoding the client's 1× figure would make the software compute a statutory underpayment. | ☐ |
| **C6** | project profit and loss | **BLOCKED** | No project P&L exists, and the project page **refuses to be one by design**: *"no revenue total, no cost total, no margin, no profit, no net, no balance … it does not do the subtraction"* [projectview.py:11-15](projectview.py#L11-L15), route `GET,POST /projects/view/<id>` [projectview.py:82](projectview.py#L82). The only margin arithmetic in the app is `purchase.job_cost()` [purchase.py:280](purchase.py#L280), which is scoped to a **quotation**, not a project, and ignores recorded charges entirely. Blocked on the labour-cost authority decision; see §5. | The decision first. Then: planned margin from the BOQ against actual cost from POs and charges, and an explicit reversal of `projectview.py`'s standing prohibition — that docstring is a deliberate guard and must be amended, not ignored. | ☐ |

---

## 5. BLOCKED

### C3 — merged RA · blocked on BQ1, which is blocked on BQ2

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

### Phase-wide gate — not an item status

Distinct from the two above, and deliberately kept out of the per-item column:
**MG/SF/2026-02 is sent and unsigned**, and the `CLIENT_CHANGES.md` §0 gate
applies to `CLIENT_CHANGES-2.md` in full. Every one of the twenty items is
gated from being *started* regardless of the status recorded against it. The
tables above report what the code does, not what may be worked on.

---

## 6. CODE vs DOCS

Recorded, not fixed. Nothing in this section was corrected in this pass.

**A. A6's latest-bill-only restriction is real — verified, not assumed.**
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
built."** That is [CLIENT_CHANGES-2.md:5](CLIENT_CHANGES-2.md#L5). It is wrong
by this audit: A4 is built and tested, and A1, A5 and A6 each stand partly on
shipped code. CC-2's own A6 section already contradicts its header by
documenting three built routes. The header was not amended when that section was
added on 23 August 2026.

**D. The client register presents Outstanding with no caveat.** CC-2's A4 note
says the figure is only as correct as the A5 write-off field makes it, and *"do
not quietly present the figure as authoritative"*. A5 does not exist, and
[client.py:280](client.py#L280) renders the figure with no qualification beyond
an *"in credit"* note when it is negative. Compounding it: `received_val`
[client.py:112](client.py#L112) sums every receipt regardless of mode, so the
one workaround available today — a `mode="adjustment"` receipt — makes
Outstanding right by making **Received** wrong.

**E. `charge.py` is named for a module it is not.** Its title is *"Employee &
Miscellaneous Charges Ledger"* [charge.py:2](charge.py#L2) and the dashboard
card reads *"Employee & Misc Charges"* [dashboard.py:1614](dashboard.py#L1614).
There is no employee record behind either. Anyone auditing C4 by name will find
these and conclude an employee master exists. It does not.

**F. `projectview.py` carries a standing prohibition that C6 requires be
reversed.** [projectview.py:11-15](projectview.py#L11-L15) forbids the page from
showing any figure that exists only by combining two panels — *"no revenue
total, no cost total, no margin, no profit, no net, no balance"* — because *"the
moment it does, the project page becomes a P&L that nobody signed off on."* C6
is that P&L. Not a contradiction today, but the guard is deliberate and must be
amended in the same pass that builds C6, not silently overridden.

**G. `ra.py` still states the dead premise in code.**
[ra.py:216-218](ra.py#L216-L218): *"No 16-character cap. That is Rule 46(b)'s
limit on a TAX INVOICE number, and **this document is not one**."*
[DOMAIN.md:347](DOMAIN.md#L347) §4 and PHASE4_RA_DESIGN.md's
`[AMENDED 8 Aug 2026]` note both rule that it **is** one. Already tracked as
row 3 of [STATE.md:494](STATE.md#L494); restated here because BQ2 cannot be
closed without correcting it, and C3 cannot start without BQ2.

---

## 7. Legend

- **BUILT** — code exists **and** tests cover it. Nothing was upgraded to BUILT on the basis of having been opened in a browser.
- **PARTIAL** — some of it exists; the "What is left" column names precisely what does not.
- **NOT STARTED** — no code. Written in preference to guessing wherever evidence was absent.
- **BLOCKED** — cannot be built until a named decision is taken by a named owner. §5 carries both.

The **Browser?** column is ticked by hand after someone has actually opened the
page. It is never filled in by a generated pass.
