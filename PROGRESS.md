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
| **Date** | 27 August 2026 *(the day's third pass — the privilege-escalation attack on `/users/*`. The escaping and adversarial pass was the first, ending at `a06f6ea`; break-glass recovery was the second, ending at `eff0034`)* |
| **Machine** | home laptop — `c:\Users\manas\OneDrive\Desktop\Demo_Works` |
| **Branch** | `antigravity-dev` |
| **HEAD** | `eff0034` — *"docs: gap 21 closed, and the test table that four files had already moved"*, the docs commit closing the previous pass. This edition is written **into** the Part A commit of the current pass rather than after it, so the code it describes is `auth.py` as that commit leaves it. |
| **vs `origin/antigravity-dev`** | **7 ahead, 0 behind, unpushed** at the start of this pass — measured with `git rev-list --left-right --count`, not assumed. Five are the escaping fix, the adversarial test file, one commit per hole it found, and that pass's docs commit; the sixth is the break-glass tool and the seventh its docs. This pass adds **three**, one per part — the escalation fix, the logout control, and permission-filtered navigation — taking it to **10 ahead, unpushed**. |
| **Dirty files** | 0 — `git status --porcelain` empty at the start of this pass, and empty again at the end of it. |
| **Test figure** | **measured this pass: 1,079 passed, 1 skipped.** Configuration: global `C:\Program Files\Python310` (CPython 3.10.11), **no `.venv`**, openpyxl **absent**, both client workbooks **absent**. The baseline it moved from was **1,062 passed / 1 skipped**, re-measured in the same configuration at the start of the pass rather than quoted — it matched. <br><br>The `.venv` configuration (CPython 3.10.11, **openpyxl 3.1.5 present**, workbooks absent) reports **1,080 passed, 3 skipped** against this commit, and **1,063 / 3** against the pre-pass code — both measured, neither derived. The third configuration (*openpyxl present, workbooks present*) is still unmeasured — neither client workbook is on this box (`fixtures/` holds only its README). <br><br>+17 in `tests/test_privilege_escalation.py`, of which **7 fail against the pre-fix `auth.py`** — verified by checking out `HEAD:auth.py`, running the file against it, and restoring. <br><br>✅ **No golden was re-baselined and none moved** — no golden file is modified in the working tree and `tests/test_print_golden.py` passes unchanged. `docs/ACCESS_MATRIX.md` **was** regenerated: its 7×61 grid is unchanged, and the two lines that moved are the Director's plain-English paragraphs, which no longer say a Director may "assign any existing role" full stop. |

**Item source.** `CLIENT_CHANGES-2.md` only. Count found: **3A ×6 (A1–A6),
3B ×8 (B1–B8), 3C ×6 (C1–C6) = 20.** Matches expectation.

---

## 2. Bars

Only BUILT fills the bar. PARTIAL contributes nothing; BLOCKED contributes
nothing.

```
ALL  ██████░░░░░░░░░░░░░░   6 of 20 BUILT · 3 PARTIAL · 2 BLOCKED ·  9 NOT STARTED
3A   ███░░░░░░░░░░░░░░░░░   1 of 6 BUILT · 3 PARTIAL · 0 BLOCKED ·  2 NOT STARTED
3B   ████████████▌░░░░░░░   5 of 8 BUILT · 0 PARTIAL · 0 BLOCKED ·  3 NOT STARTED
3C   ░░░░░░░░░░░░░░░░░░░░   0 of 6 BUILT · 0 PARTIAL · 2 BLOCKED ·  4 NOT STARTED
```

⚠ **Only B1–B5 were authorised.** The 26 August 2026 OVERRIDE block in
`CLIENT_CHANGES.md` §0 names those five items and no others. B6, B7 and B8 are
NOT STARTED *and still gated*, as is every remaining item of 3A and 3C — a
filled bar is not permission to fill the next one.

---

## 3. What the bars do not say

**The item count does not measure the work.** These twenty items are not
comparable units and the ratio 6/20 is close to meaningless as a measure of
effort remaining. A2 is a column on one form. B5 was a decision applied to every
route in the application.

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

Two items now dominate what is left of Phase 3:

- **B8 — file attachments.** The first thing that breaks the storage model.
  There is no `/static`, images are base64 data URIs, and `boq.MAX_JSON_BYTES`
  is 300,000 ([boq.py:192](boq.py#L192)) against a photographed supplier bill
  of 2–5 MB. This is new infrastructure — a real file store, a path on the
  record, a size and type gate, and cascade delete — not a field.
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
| **A1** | PO base rate editable | PARTIAL | Editable **at creation**: `RATE_PREFILL_FIELD = "supply_base_rate"` [purchase.py:182](purchase.py#L182); rate box rendered and stored on `GET,POST /purchase/from-boq/<boq_id>` [purchase.py:1662](purchase.py#L1662) and `GET,POST /purchase/from-draft/<draft_id>` [purchase.py:1797](purchase.py#L1797). Test `test_rates_prefill_from_the_supply_base_rate_and_an_edit_is_what_is_stored` [tests/test_boq_to_po.py:240](tests/test_boq_to_po.py#L240). | Editing the rate on an **existing** PO. `POST /purchase/<id>/update` [purchase.py:2030](purchase.py#L2030) is status-and-note only; its docstring states the commercial content of an issued PO is deliberately not editable there. No route anywhere changes a stored PO line rate. | ☐ |
| **A2** | Discount column on final PO | NOT STARTED | The string `discount` does not occur in any application `.py` file. The only repo-wide hit is `.venv/.../rich/_emoji_codes.py`. | All of it: form column, per-line or document-level storage, and the effect on `_totals_of()` [purchase.py:589](purchase.py#L589). | ☐ |
| **A3** | Additional charge lines on final PO | NOT STARTED | No repeater on the PO. No `additional_charge` / `extra_charge` / `loading` / `transportation` field in `purchase.py`. The seed pattern CC-2 points at exists but serves the charges ledger, not the PO: `CHARGE_HEADS_RECORD` [settings.py:353](settings.py#L353), `charge_heads()` [settings.py:361](settings.py#L361). | All of it. Build **one** label+amount repeater seeded from `/settings`, per CC-2's A3 note — not four fields. | ☐ |
| **A4** | Total outstanding on client register | **BUILT** | Computed at [client.py:120](client.py#L120) from `issued_val` [client.py:110](client.py#L110) less `received_val` [client.py:112](client.py#L112); rendered on `GET /clients/` [client.py:219](client.py#L219) at [client.py:280](client.py#L280). Tests `test_outstanding_counts_issued_bills_only` [tests/test_client_segregation.py:151](tests/test_client_segregation.py#L151) and `test_receipts_reduce_outstanding_and_an_overpayment_shows_as_credit` [tests/test_client_segregation.py:173](tests/test_client_segregation.py#L173). | Nothing for A4 itself. **But see §6-D:** CC-2's A4 caveat requires the figure not be presented as authoritative until A5 exists, and the page carries no such caveat. | ☐ |
| **A5** | Write-off / adjustment on a payment | PARTIAL | No write-off field exists on any record. What exists is an adjacent pre-existing capability: receipt mode `"adjustment"` in `RECEIPT_MODES` [ra.py:138](ra.py#L138), offered by `_mode_options()` [receipt.py:326](receipt.py#L326) on `GET,POST /receipts/new` [receipt.py:510](receipt.py#L510). The mode list is covered by `test_the_mode_picker_is_a_select_over_the_shared_list` [tests/test_receipts.py:751](tests/test_receipts.py#L751). | The field itself. Today the only way to clear a short-allowed balance is to file a **second receipt** with `mode="adjustment"` — which does reduce Outstanding, but `received_val` [client.py:112](client.py#L112) sums receipt amounts **without inspecting mode**, so the register's "Received" figure is inflated by every write-off. A5 as specified is a field on the payment, producing no document and no number series. | ☐ |
| **A6** | RA edit and delete — draft only | PARTIAL | All three routes exist and are gated: `GET,POST /ra/cancel/<id>` [ra.py:2740](ra.py#L2740) gated by `can_cancel()` [ra.py:1578](ra.py#L1578); `GET,POST /ra/edit/<id>` [ra.py:3011](ra.py#L3011) gated by `can_edit()` [ra.py:1470](ra.py#L1470); `GET,POST /ra/delete/<id>` [ra.py:3796](ra.py#L3796) gated by `can_delete()` [ra.py:1512](ra.py#L1512). Tests: `test_the_latest_bill_can_be_edited` [tests/test_ra_routes.py:378](tests/test_ra_routes.py#L378), `test_the_latest_bill_can_be_deleted_and_the_number_is_reused` [tests/test_ra_routes.py:748](tests/test_ra_routes.py#L748), `test_a_cancelled_bill_cannot_be_un_cancelled_edited_or_deleted` [tests/test_ra_routes.py:535](tests/test_ra_routes.py#L535). | **The latest-bill-only restriction, verified as real — see §6-A.** A draft that is not the highest `ra_no` on its BOQ is refused **both** edit and delete. CC-2's A6 wording narrows to draft-only and stops there; it does not narrow to latest-only. Whether A6-as-sold covers lifting that is a commercial question, not a code one. | ☐ |

### 3B — users, access and approvals

⚠ **Nothing in this section changed build state on 27 August 2026** — across
three passes that day. The first escaped user text everywhere it reaches HTML
and **attacked** the layer B1–B5 shipped; the second added break-glass password
recovery and a second Owner; the third attacked `/users/*` as a Director and
**found a privilege escalation**. None of them built a Phase 3 item and none
started anything gated. B1–B5 stay BUILT, B6–B8 stay NOT STARTED and gated.
What changed is how much of B1–B5 is *verified* rather than asserted, and that
is recorded in the B1, B3, B5 and B6 rows below.

⚠ **A BUILT item can still be wrong.** B3 was marked BUILT on 26 August with
`_may_grant()` cited as the thing that holds it, and it did hold the door it was
written for. The escalation found on 27 August walked through a **different**
door on the same page — the password field — which no cell in this table had
ever claimed anything about. **Read a BUILT row as "this exists and these tests
hold it", never as "this was attacked".** [STATE.md §1.12](STATE.md) is the plain-English account;
[docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md) is the generated 7×61 grid, with
every cell marked specification-or-derivation.

**B1–B5 built 26 August 2026** in [auth.py](auth.py) (1,670 lines), under the
dated **26 August 2026 OVERRIDE** in `CLIENT_CHANGES.md` §0. The application is
now closed: `auth.enforce(app)` [app.py:158](app.py#L158) installs a single
`before_request` gate that refuses **any** of the 72 endpoints not classified in
`auth.ROUTE_PERMISSIONS` [auth.py:236](auth.py#L236).

The `SECRET_KEY` demo fallback recorded here on 25 August is **gone**:
`auth.resolve_secret_key()` [auth.py:70](auth.py#L70) reads
`SAMRUDDHI_SECRET_KEY`, then `SECRET_KEY`, then a gitignored `secret_key.txt`,
with no hardcoded fallback. ABOUT.md §7 gap 8 is closed.

**B6, B7 and B8 remain NOT STARTED and remain gated.**

⚠ **Two deliberate deviations from CLIENT_CHANGES-2.md**, both decided by the
client-facing owner before code was written and both recorded in the override
block: B5's two-stage audit-mode rollout was collapsed into immediate
enforcement (with the logging half kept as a condition), and B3's **Owner** tier
ships as a seventh role beside B4's six. Do not read either as spec drift.

| Tag | Requirement (short) | Status | Evidence | What is left | Browser? |
|---|---|---|---|---|---|
| **B1** | user accounts and login | **BUILT** | `users` collection [store.py:44](store.py#L44), persisted via [db.py:75](db.py#L75). `GET,POST /login` `auth.login()` [auth.py:944](auth.py#L944); `GET,POST /logout` [auth.py:990](auth.py#L990) (GET confirms, POST destroys); `GET,POST /setup` [auth.py:1090](auth.py#L1090); `GET,POST /account` [auth.py:1025](auth.py#L1025). Hashing is `werkzeug.security` — `create_user()` [auth.py:508](auth.py#L508). `SECRET_KEY` moved: `resolve_secret_key()` [auth.py:70](auth.py#L70). Bootstrap also non-interactive: [tools/seed_users.py](tools/seed_users.py). Tests: `test_a_correct_password_signs_in`, `test_a_wrong_password_does_not`, `test_a_deactivated_user_cannot_sign_in`, `test_logout_needs_a_post`, `test_the_demo_secret_key_is_gone_from_the_codebase` [tests/test_auth.py](tests/test_auth.py). | Nothing for B1. ✅ **§7 gap 21 is closed (27 Aug 2026)** — it needed a decision, the decision was *both*, and the install had already walked into the failure it described: the seeded Owner's password was recorded nowhere. [tools/set_password.py](tools/set_password.py) is the break-glass CLI and a **second active Owner** is the operational half. **§7 gap 22 is still open** — no rate limiting on `/login`, still not a code fix until a decision is taken. <br><br>✅ **27 Aug 2026:** `/login`'s username-enumeration **timing** oracle is closed (§7 gap 25) — a real username took 70 ms to reject and an unknown one 0.3 ms, **239x**, because only the real one hashed. The not-found path now hashes against `_DUMMY_HASH`; measured 1.00x. Gap 22 is **narrowed, not closed**. | ☑ |
| **B2** | permissions are named strings, minted in code | **BUILT** | 61 permissions in `auth.PERMISSIONS` [auth.py:120](auth.py#L120), each with a label and display group, derived from `app.url_map`. Roles are editable data: `GET,POST /roles/edit/<id>` [auth.py:1562](auth.py#L1562) renders checkboxes over the catalogue. The client cannot mint a string — `_posted_permissions()` [auth.py:1514](auth.py#L1514) drops anything not a catalogue key. Effective permissions are the **union** of roles: `permissions_of()` [auth.py:540](auth.py#L540). Tests: `test_a_role_cannot_be_given_a_permission_that_does_not_exist`, `test_editing_a_role_takes_effect_without_signing_in_again`, `test_every_catalogue_permission_gates_something` [tests/test_access_control.py](tests/test_access_control.py). | Nothing for B2. **Deviation from CC-2's wording:** the assignment surface is `/roles`, not `/settings`. `/settings` is the company-identity form and mixing an access matrix into it would put a lockout one mis-click from a bank-details save. | ☑ |
| **B3** | Owner / Admin split | **BUILT** | Modelled as *"Owner is exactly whoever holds `admin.roles`"* — `is_owner()` [auth.py:557](auth.py#L557) — so there is no tier field to disagree with the permissions beside it. Only an Owner may grant an Owner role: `_may_grant()` [auth.py:1150](auth.py#L1150). The last active Owner cannot be deactivated **or edited out of the tier**: `_would_strand_install()` [auth.py:1169](auth.py#L1169). Role floors: `_role_edit_refusal()` [auth.py:1197](auth.py#L1197). Tests: `test_the_last_owner_cannot_be_deactivated`, `test_the_last_owner_cannot_edit_their_own_owner_role_away`, `test_an_admin_cannot_grant_themselves_the_owner_role`, `test_an_admin_can_still_create_an_ordinary_user`, `test_the_owner_role_cannot_lose_the_permission_that_defines_it`. | ✅ **27 Aug 2026:** the recovery hole is closed. *"More than one Owner is permitted and untested in anger; a single-Owner install has no recovery path if that password is lost"* — that was written the day before this install proved it, and it is no longer true of this install: **two active accounts hold `admin.roles`**, either can reset the other at `/users/edit/<id>`, and [tools/set_password.py](tools/set_password.py) is the path back in when neither can sign in. Both were driven through the real `/login` against live MySQL — 33 of 33 checks. ⚠ **Still open:** password reset is **undocumented for the client** — `/account` says only *"an Owner sets a new password for you"*. That is the half of §7 gap 21 this pass did not close, and it is a client-facing writing job, not code. <br><br>🔴 **27 Aug 2026, the day's third pass: the tier split had a hole in it, and it was the password field this row had just finished celebrating.** `/users/edit/<id>` sets a password for any account `admin.users` can load. A **Director-only** account set the **Owner's** password, changed no role, signed in as the Owner and reached `/roles` with a 200 — the one page B3 says they may never reach. Four more of the same shape got through: the Owner role taken **off** a spare Owner, an Owner deactivated, a dormant Owner reactivated, and a limited `admin.users` role conferring `charge.*` it does not hold. ✅ **Closed in the same pass.** `_may_grant()` [auth.py:1181](auth.py#L1181) now tests the **whole** permission set of every role assigned, not just `admin.roles`; `_may_administer()` [auth.py:1227](auth.py#L1227) is its mirror and refuses any change to an account holding a permission the actor lacks; `_administer_refusal()` [auth.py:1272](auth.py#L1272) renders and **logs** it. Guards `/users/edit`, `/users/deactivate`, `/users/activate`, GET and POST. 17 tests in [tests/test_privilege_escalation.py](tests/test_privilege_escalation.py), **7 failing against the pre-fix code**. §7 gap 26; [STATE.md §1.14](STATE.md). 📌 **Tightened past the letter of B3**: a Director can no longer administer an Owner account at all, which B3 does not ask for — the reasoning is in gap 26. | ☑ |
| **B4** | roles as discussed | **BUILT** | Seven builtin roles seeded idempotently by `ensure_builtin_roles()` [auth.py:469](auth.py#L469) from `BUILTIN_ROLES` [auth.py:392](auth.py#L392) — B4's six plus B3's Owner. Multi-role assignment is a checkbox list on `/users/create` and `/users/edit`; effective permissions are the union. HR restriction applied literally to `charge.*`, the wages ledger being the only employee data the app holds. Tests: `test_the_six_client_roles_and_the_owner_are_seeded`, `test_hr_information_is_kept_from_sales_purchase_and_accounts`, `test_permissions_are_the_union_of_several_roles`, `test_re_seeding_does_not_undo_an_owners_edit`. | ⚠ **The per-role permission sets are a derived starting position, not a client instruction.** CC-2 carries **no per-role grid** — B4 names the roles and states one restriction. Walk the seven roles through with the client. HR's real surface arrives with C4 (employee master); until then HR holds only the charge ledger. | ☑ |
| **B5** | default deny, rolled out in audit mode | **BUILT — with a recorded deviation** | Central registry `ROUTE_PERMISSIONS` [auth.py:236](auth.py#L236) classifying all 72 endpoints; single hook `_gate()` [auth.py:669](auth.py#L669) installed by `enforce()` [auth.py:740](auth.py#L740) at [app.py:158](app.py#L158). **Absence refuses** — proved, not claimed, by `test_an_unregistered_endpoint_is_refused`. The sweep CC-2 asks for is `test_every_endpoint_is_classified`, over `app.url_map`; `test_no_non_public_endpoint_is_reachable_without_a_session` sweeps every endpoint anonymously. 13 tests in [tests/test_access_control.py](tests/test_access_control.py). | ⚠ **Audit mode was not run.** CC-2 asks for log-only then flip; this enforces from the start, by decision recorded in the override block. **The logging half was kept as the condition of that decision** — every refusal records user, endpoint, permission and reason to `REFUSAL_LOG` [auth.py:626](auth.py#L626) and `app.logger`, readable at `GET /access-log` [auth.py:1604](auth.py#L1604). Also: the registry is **endpoint-level only** — §7 gap 24, which B6 inherits. <br><br>✅ **27 Aug 2026, verified by attack rather than by its own tests.** Eleven adversarial probes in [tests/test_access_control_adversarial.py](tests/test_access_control_adversarial.py); **nine clean, two holes**. Forged/unsigned cookies refused, deactivation and role edits landing on the next request, all 7 roles correct on every admin URL by direct hit, every lockout guard refusing a direct POST, `/setup` refusing a POST, no error page rendering before the gate, a route added to the live `url_map` refused even to an Owner, and the refusal log carrying no credentials. The holes were the timing oracle (B1's cell) and **§7 gap 24b** — `POST /projects/view/<id>` wrote under the read permission `project.view`, because one endpoint carries one permission across both methods. Fixed with a per-view guard; a sweep now fails on any future rule that accepts POST under a `*.view` permission. | ☑ |
| **B6** | approvals | NOT STARTED | No approval state on any record. Every occurrence of "approve/approved" in application code refers to BOQ **approved quantity** — e.g. [challan.py:249](challan.py#L249), [boq.py:2141](boq.py#L2141) — not to an approval ladder. `purchase.py` states the opposite explicitly: *"There is no extra approval step on this path"* [purchase.py:1511](purchase.py#L1511). | All of it, including the load-bearing creator-cannot-approve rule checked against the record's creator. Cannot start before B1. <br><br>✅ **One prerequisite is now met.** CC-2's *"Security items promoted by this phase"* named a stored XSS in `product.py`/`quotation.py` as the thing that *"lets one user hijack another's session and approve their own submissions"* — i.e. it defeats exactly this ladder. Closed 27 Aug 2026 (§7.7, §7.9d, §7.9e), and the defect turned out to reach fifteen further files. **B6 is still gated and still NOT STARTED**; what changed is that it is no longer being planned on top of a known session-theft hole. | ☐ |
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
