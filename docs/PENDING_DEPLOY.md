# PENDING_DEPLOY — everything production has not got yet

> **This file is the INPUT to one consolidated production deploy.** It is not a
> plan and not a decision: it is the list of what is on `antigravity-dev` and
> not on the box, grouped by feature, with every step production needs beside
> the feature that needs it.
>
> **It does not replace [DEPLOY.md](../DEPLOY.md).** That file owns how the box
> is built and what the go-live checklist is; this one owns *what is
> outstanding right now*. Where a step here has a §, it is DEPLOY.md's.
>
> ⚠ **Nothing below has been run.** This was written on a cloud checkout with
> **no MySQL**, no production credentials and no access to the box. Every
> figure is measured on that checkout; every instruction is to be carried out
> by a human on the server.

---

> ### ⚠ 31 OCTOBER 2026 — THIS FILE'S "PRODUCTION IS AT" IS STALE
>
> **Measured on the box on 31 October 2026 (read-only gate run): production
> was NOT at `3d4692c`.** A full deploy ran on 30 October (`0341841` →
> `cf47a81`), so every commit listed below is already on the box, and the
> 30 October suite run there was **5,175 passed · 131 skipped · 0 failed**.
> On top of `cf47a81` the box carries **`a121953`, committed locally and never
> pushed** (a CSS fix for 17 register pages, in the checkout but not yet
> served at the time of the check).
>
> The PO item dropdown hotfix (CLIENT_CHANGES.md §0 **sixtieth** block) was
> first cut as `hotfix/po-item-picker` off `c6a385a` on the stale belief above;
> that branch is now **unused**. It reaches prod as `antigravity-dev`
> (`fc5f4ed` merged at `da66ae0`), merged on the box into `a121953` — a merge,
> not a fast-forward, because of that local commit. **Until `a121953` and the
> box's merge commit are pushed back to GitHub, the box is ahead of origin.**

## 0. Where production is, and where this line is

| | |
|---|---|
| **Production is at** | `3d4692c` — *"Bring prod-only edits from samruddhi-prod (00122b9) into repo"*, 24 October 2026 |
| **This line is at** | `1eb36ca` (see §1) |
| **Commits outstanding** | **34** |
| **§0 blocks outstanding** | fifty-third, fifty-fourth, fifty-fifth, fifty-sixth, fifty-seventh, fifty-eighth, **fifty-ninth** |
| **Suite on this checkout** | **5,280 passed · 26 skipped · 0 failed** (CPython 3.13.17, dependencies from `requirements.txt` + `pytest==9.1.1`, **client workbooks absent**) |

⚠ **The suite total depends on the environment** — ABOUT.md §1 owns the table.
26 skipped here is the no-workbooks configuration (it was 20 before the §0
fifty-ninth block; the six new skips are `tests/test_sign_stamp.py`'s
nine-document sweep skipping the three documents that never carried the
"Computer Generated Document" line). On the production box the total will
differ and that is expected; what matters is **0 failed**.

⚠ **The measured baseline this line started from was 4,920 / 20 at
`83d4ef5`**, and it was re-measured on this checkout rather than quoted. The
fifty-ninth block added **+360 passed and +6 skipped**.

---

## 1. The 24 commits, oldest first

| # | SHA | What |
|---|---|---|
| 1 | `c35b710` | Preloaded signature and company stamp on every signed print (§0 **53rd**, change 1) |
| 2 | `02f1e10` | Make column on the purchase order and the draft PO (§0 53rd, change 2) |
| 3 | `c6a385a` | No browser header or footer on a printed document (§0 53rd, change 3) |
| 4 | `5132ee3` | §0 **fifty-fourth** block — the 27 October call |
| 5 | `8904422` | A document number typed by hand, forward only (§0 54th, item A) |
| 6 | `2ce5d6f` | A search on the attendance pages (§0 54th, item B) |
| 7 | `0341841` | Audits C and D — the rounding finding recorded (ABOUT.md §7 gap 84). **Docs only** |
| 8 | `1fdc09e` | HSN editable on an issued purchase order's lines (`/purchase/edit`) |
| 9 | `a6ab6c4` | Project page: documents follow their BOQ, revisions no longer stacked |
| 10 | `9b94016` | §0 **fifty-fifth** block — the payslip and the attendance import |
| 11 | `078e1e3` | Attendance: half day and paid leave; the payslip's month reader |
| 12 | `de9d757` | The payslip, the pay ledger and the attendance workbook import |
| 13 | `f99c705` | §0 **fifty-sixth** block — a bigger SF mark, a Director's access page |
| 14 | `ff7e956` | The SF mark 1.5× on the letterhead banner (§0 56th, item 1) |
| 15 | `93c09e7` | Staff access: a login's own ALLOW and BLOCK lists (§0 56th, item 2) |
| 16 | `90162b9` | §0 **fifty-seventh** block — the SF mark 1.5× on screen |
| 17 | `c62f96a` | The SF mark 1.5× on screen |
| 18 | `702a98e` | §0 **fifty-eighth** block — the project page becomes the job's own page |
| 19 | `19dc55d` | A BOQ makes its own project (§0 58th, item 1) |
| 20 | `7f2fd07` | Labour lands on the project by itself (§0 58th, item 2) |
| 21 | `7308d26` | Attach a loose document to a project by hand (§0 58th, item 3) |
| 22 | `456c980` | The project P&L, one click away (§0 58th, item 4) |
| 23 | `e793dfa` | The waterfall and the progress spider (§0 58th, item 5) |
| 24 | `976010d` | RA · Supply & Installation in one POST; C1's prerequisite off (§0 58th, item 6) |
| 25 | `83d4ef5` | `docs/PENDING_DEPLOY.md` — this file's first version. **Docs only** |
| 26 | `2ffabf8` | §0 **fifty-ninth** block — the 26 October rulings rebuilt, and the 28 October leftovers. **Docs only** |
| 27 | `17b2aba` | HSN editable everywhere, fill blanks only, one predicate (§0 59th, **A1**) |
| 28 | `b0e4809` | The Product Inquiry is fully editable until converted (§0 59th, **A2**) |
| 29 | `d08ed3a` | Make prefills off the BOQ import remark — §7 gap 81 closed (§0 59th, **A3**) |
| 30 | `a22b26d` | A signed sheet stops saying it needs no signature (§0 59th, **A4**) |
| 31 | `66759ef` | The Draft PO is displayed as **Product Inquiry** (§0 59th, **B1**) |
| 32 | `3eded00` | Named, reusable pictures on the inquiry and the real PO (§0 59th, **B2**) |
| 33 | `6ea528a` | A units dropdown with its GST UQC (§0 59th, **B3**) |
| 34 | `1eb36ca` | A BOQ revision numbered off its root (§0 59th, **B4**) |

⚠ **The office-PC pass four of these blocks were holding a place open for does
NOT exist.** The fifty-fourth block left the draft PO out of the hand-typed
number because *"`po_draft.py` is being edited by the unpushed office-PC pass
(HSN / Draft PO editing)"*, and the fifty-fifth through fifty-eighth each
repeated that origin's block number would stand at the merge. Manas confirmed
on 29 October 2026 that the work was lost and never pushed. **There is nothing
to merge, no block number moves, and ABOUT.md §7 gaps 83 and 84 keep their
numbers** — their "this may move at a merge" notes are spent and now say so.
`1fdc09e` (#8 above) is the one piece of that pass that did land, and A1
generalises its predicate rather than rebuilding it.

---

## 2. THE ONE STEP THAT IS MANDATORY AND SILENT IF MISSED

```bash
sudo -u samruddhi .venv/bin/python tools/backup_db.py --label pre-reconcile
sudo -u samruddhi .venv/bin/python tools/reconcile_role_permissions.py          # report first
sudo -u samruddhi .venv/bin/python tools/reconcile_role_permissions.py --write  # then grant
```

⚠ **`auth.ensure_builtin_roles()` never rewrites an existing role's permission
list**, and that is correct. The cost is that **a permission minted in a later
pass reaches no live role, the Owner included** — and `auth._gate()` has no
Owner bypass, so the page it guards is unreachable by everybody and **the
symptom is silence**. This has shipped three times already (B6, C4/C5, C2).

**Six permissions were minted since production:**

| permission | from | granted to, by default |
|---|---|---|
| `payroll.view` | `de9d757` (§0 55th) | Owner, Director, HR |
| `payroll.edit` | `de9d757` | Owner, Director, HR |
| `payroll.issue` | `de9d757` | Owner, Director, HR |
| `payroll.import` | `de9d757` | Owner, Director, HR |
| `payroll.delete` | `de9d757` | Owner, Director, HR *(Owner-only on 2 routes)* |
| `docnum.override` | `8904422` (§0 54th, item A) | Owner, Director — a **panel** permission |

⚠ **The §0 fifty-eighth block minted NONE.** Its one new endpoint,
`/raboth/create`, is classified under the **existing** `ra.create`; the P&L's
`project.pnl` already existed (8 October 2026) and only gained `dashboard.index`
in its `PANEL_PERMISSIONS` tuple, which grants nothing new. `project.edit`
gates the new *Attach document* control and already existed.

⚠ **The §0 FIFTY-NINTH block minted NONE either.** Its four new endpoints —
`/boq/hsn/<id>`, `/proforma/hsn/<id>`, `/invoice/hsn/<id>` and
`/ra/hsn/<id>` — are classified under the **existing** `boq.create`,
`proforma.create`, `invoice.create` and `ra.edit`, so none of them grants
access a reader did not already have. `docs/ACCESS_MATRIX.md` moved **203 →
207 endpoints with 91 permissions unchanged**.

⚠ **B1 renamed the five `po.*` permission DESCRIPTIONS and NOT their IDS**,
which is the whole reason it needs no reconcile. A renamed id would have
reached no live role — `ensure_builtin_roles()` never rewrites an existing
role's list — and the page it guards would be unreachable by everybody, an
Owner included, with silence as the symptom. `tests/test_product_inquiry_name.py`
asserts each of the five ids.

**So the reconcile above is for the payroll pass and `docnum.override`, and
nothing in the two most recent blocks depends on it.**

⚠ **Granting a permission is a decision about who may do what.** The tool
refuses to take it silently: run it **without** `--write` first, read the
report, and only then write. See `tools/reconcile_role_permissions.py`'s header
and DEPLOY.md §9.4a.

---

## 3. Requirements — nothing changed

```
git diff 3d4692c..HEAD -- requirements.txt    # empty
```

No dependency was added, removed or re-pinned in any of the 34 commits. **No
`pip install` step is needed.** `openpyxl` and `xlrd`, which the attendance
workbook import reads, were already runtime pins from 29 September 2026.

⚠ **The §0 fifty-ninth block added no dependency either.** The named-picture
library (B2) re-uses `lineimage.py`'s existing Pillow re-encode, which is
imported **inside `save()`** — so a box without Pillow still boots, still
renders every picker, and says the upload is unavailable, exactly as it has
since 21 October 2026.

---

## 4. Migrations — ONE tool, NOT run, `--dry-run` first

| tool | from | status |
|---|---|---|
| `tools/backfill_marking_projects.py` | pre-dates production | **unchanged** by these commits |
| `tools/clean_units.py` | `6ea528a` (§0 59th, **B3**) | ⚠ **NEW, and NOT RUN.** Dry run by default |

⚠ **The 34 commits ship NO new migration, and that is by design.** Every data
shape they add is written forward only and absent means something definite:

- `number_override` (§0 54th) — absent means *minted by the counter*
- `rate_model` / the two new muster statuses (§0 55th) — a record without them
  reads exactly as it did
- `created_from: "boq"` (§0 58th item 1) — **provenance only, nothing branches
  on it**; absent means *made by hand*
- `project_trail` (§0 58th item 3) — absent means *never moved by hand*
- `raised_as_both` (§0 58th item 6) — absent means *raised on its own*, and the
  set rules never touch such a record

And from the **fifty-ninth** block:

- `hsn_trail` (A1) — absent means *no code was ever filled by hand*
- `hsn` on a product-inquiry line (A2) — absent means *the schedule had none*
- `image_name` on a PI / PO / inquiry line (B2) — absent means *no caption*,
  and such a line prints the Image cell it always printed
- `line_image_library` (B2) — a **new collection**, empty on arrival. ⚠ Add the
  key to nothing by hand: `db.COLLECTIONS` carries it and **the table is
  created automatically on next start** (ABOUT.md §4)
- `unit_list` (B3) — a `STORE["settings"]` record; **absent means no custom
  units, which is the normal and likely state**
- a BOQ revision's `/1` suffix (B4) — ⚠ **forward only. Every revision already
  on the box keeps its series number**, is never rewritten, and reads
  correctly: `pipeline.root_ref()` leaves a ref with no suffix alone

**Nothing is backfilled and nothing needs to be.** If a later pass ever does
need one, it ships as an idempotent tool with `--dry-run` and is run by a human
after a backup, which is this repo's standing rule.

### 4.1 `tools/clean_units.py` — NEW, and deliberately NOT RUN

B3's own ask. The seven shared units are offered everywhere from this deploy,
and **every unit already on a record is left exactly as it is** — a line that
says `Lump Sum` goes on saying it and the dropdown keeps it as an option on
that line. This tool is the separate, human-run cleanup.

```bash
sudo -u samruddhi .venv/bin/python tools/backup_db.py --label pre-unit-clean
sudo -u samruddhi .venv/bin/python tools/clean_units.py                 # dry run
sudo -u samruddhi .venv/bin/python tools/clean_units.py --write         # BOQs + specs
```

- [ ] ⚠ **Read the dry run before `--write`.** It prints three things that
      matter: the rows it would change, the **judgement rows** (`Lump Sum` and
      `Job` → `Lot`, which is the one judgement in its table), and **every
      string it cannot point at**, which it leaves alone and names
- [ ] ⚠ **It does NOT touch a document that has been SENT** — a proforma, a
      tax invoice, an RA bill, a purchase order, a product inquiry, a challan
      or a work order — without `--include-issued`. Each of those is a
      snapshot of what was sent; changing a unit on one changes a document the
      customer already has. **Do not pass that flag without asking the client**
- [ ] It is idempotent: a second dry run should report every row as `exact`

⚠ **It has never been run anywhere**, including on this checkout, which has no
MySQL. The figures it would print are unknown.

⚠ **No database backup was taken before any of this work** because there is no
MySQL on the machine it was built on and none was possible. The backup in §2 is
the first one in this sequence and must be real.

---

## 5. Feature by feature — what the box needs beside the code

### 5.1 Signature and company stamp on every signed print — `c35b710` (§0 53rd)

**Needs a human with the artwork, at `/settings`, as an OWNER.**

- [ ] Sign in as an **Owner** (a Director is refused with a 403 and is not even
      shown the control) and open `/settings`
- [ ] **Signature & Stamp** section → upload the director's signature
- [ ] → upload the round company stamp
- [ ] Print one document of each type and read the foot: both must sit above
      *Authorised Signatory*

Storage is `SIGNATURE_IMAGE` / `STAMP_IMAGE` on the company settings record as
PNG data URIs, re-encoded from the pixels alone (no metadata), 600 px long
side. **No route and no permission** — nothing to reconcile.

⚠ **Until these are uploaded every signed document prints exactly as it does
today.** The feature is inert, not broken; there is nothing to roll back if the
client is not ready.

### 5.2 Starting numbers for the hand-typed document number — `8904422` (§0 54th A)

- [ ] Ask the client which series their paper book is actually running
- [ ] `/settings` → set the floors. **Leaving every box blank is the correct
      answer unless they say otherwise** (DEPLOY.md §9.7)
- [ ] Reconcile `docnum.override` — see §2

### 5.3 The payslip and the attendance import — `de9d757` (§0 55th) — **CHARGED**

- [ ] Reconcile the five `payroll.*` permissions — **see §2, mandatory**
- [ ] Confirm with HR the **opening loan balances** the first import will write
      (ABOUT.md §7 gap 87: the largest on the September sheet is ₹84,409, and
      three rows deduct ₹2,000 against no balance, which shows as −₹2,000)
- [ ] ⚠ The client's workbooks are **not** in git — they carry staff names and
      wages. The importer reads whatever is uploaded; nothing needs installing

### 5.4 The SF mark 1.5× — `ff7e956`, `c62f96a` (§0 56th/57th)

- [ ] **Copy the landing page**, which is where the only out-of-git copy lives:

```bash
sudo cp deploy/landing/index.html /var/www/samruddhi-landing/index.html
```

⚠ **`deploy/landing/index.html` in git is not the live page** — nginx serves
`/var/www/samruddhi-landing/`, a separate file, and a `git pull` does not touch
it. No nginx reload is needed for a content change. Back up the live file
first. If the logo changed, copy `assets/logo-mark-256.png` into the directory
nginx serves for `/_landing/` as well; **it did not change in these commits.**

### 5.5 Staff access, a login's own ALLOW/BLOCK lists — `93c09e7` (§0 56th item 2)

- [ ] Nothing to configure. Two new endpoints under the **existing**
      `admin.users`; no permission minted
- [ ] ⚠ Tell whoever reads `docs/ACCESS_MATRIX.md` that **it is a grid of ROLES
      and cannot show a person's list** (ABOUT.md §7 gap 90). *"Can Ashwini
      raise a proforma?"* is answered by `/access/<id>`, not by the grid

### 5.6 The project page becomes the job's own page — §0 **fifty-eighth**

- [ ] Nothing to configure, no permission minted, no migration
- [ ] ⚠ **Tell the client what changed about raising a claim**, because this is
      the one behaviour change an operator will notice:
      **a delivery challan and a measurement sheet are no longer required
      before an RA bill.** The claim still cannot exceed the approved
      quantity, and **where an approved measurement sheet exists the
      installation claim is still capped at the measured quantity** — the form
      says which cap applies on every claim
- [ ] ⚠ Tell them the **project picker on `/boq/create` now defaults to
      "New project from this BOQ"**. Existing behaviour is still there (an
      existing project, or none) and a revision never makes a project
- [ ] Watch the first few BOQs: a job spelled two ways is **one** project
      (`pipeline.norm_name()`), and a project made this way has **no site**
      until somebody links one on *Edit Project*. **Site labour needs that
      link** — it is the join key

---

### 5.7 The §0 **fifty-ninth** block — HSN, the Product Inquiry, pictures, units, revision numbers

- [ ] **Nothing to configure, no permission to reconcile, no migration to
      run.** The one tool it ships (§4.1) is a separate decision
- [ ] ⚠ **Tell the client the Draft PO is now called a PRODUCT INQUIRY** (B1).
      It is a label change only — every `/po/` link, every bookmark, every
      stored field and the `SF/DPO` series are untouched — but it is on the
      printed title, so it is the change an operator notices first
- [ ] ⚠ **Ask the client whether they want the `SF/DPO` PREFIX changed too.**
      It is their own number on their own paper book and is an editable field
      at `/settings`; this pass deliberately did not touch it
- [ ] ⚠ **Tell them what a BOQ revision is numbered now** (B4):
      `SF/BOQ/26-27/0019/1`, not the next number in the series. **Every
      revision already on the box keeps its number** and none is renumbered.
      The printed schedule and every document citing it show the **root**
      (`…/0019`) with the revision on its own row; the registers and the view
      pages show the suffix
- [ ] ⚠ **Watch the first revision raised after the deploy.** The series
      scan was taught to skip a revision suffix (`series.Series.segments`),
      because the last segment of `…/0001/2` read as an ordinal pushed the
      next **original** forward. Confirm the next new BOQ takes the number the
      client expects
- [ ] **The units dropdown is on from this deploy** (B3) — Nos, Mtrs, Kg, Set,
      Lot, Sq Ft, Sq M. ⚠ **Ask the client which of their own units to add**
      at `/settings` → *Units of Measure*, one per line as `name|UQC`. `Ltrs`,
      `Lump Sum`, `Job` and `Sq.Mtrs` are on their existing sheets and are
      **not** among the seven; leaving the box empty is a complete answer and
      every existing line keeps its own wording either way
- [ ] ⚠ **Tell whoever fills in HSN codes that there are now five places to
      do it** (A1): `/boq/hsn/<id>`, `/proforma/hsn/<id>`, `/invoice/hsn/<id>`,
      `/ra/hsn/<id>` and the purchase order's reprice form. **Only a BLANK code
      can be filled once a document is issued**; a printed one is read-only and
      a changed post is refused with nothing written. Every fill is recorded on
      the document
- [ ] **Pictures gained names** (B2). The first picture for an item is uploaded
      on a document's own **Pictures** page, with a name; after that the create
      forms for the same item offer it preselected. ⚠ **No new upload path and
      no new limit** — one file per request, as since 21 October 2026

## 6. What a human must look at after the deploy

- [ ] **`python -m pytest -q` on the server, green.** The suite no longer reads
      the checkout's `.env` (25 September 2026), so it is a usable post-deploy
      check there
- [ ] **One document of each type printed and read by a human.** ⚠ **SEVEN of
      the 34 commits DO move printed documents.** Each re-baselined
      `tests/test_print_golden.py` with its own measurement, and that is
      exactly why a human reads one: a golden proves a document did not change
      **by accident**, not that the change was right.

      | commit | what moved on paper |
      |---|---|
      | `02f1e10` | the **Make** column on the purchase order and the draft PO |
      | `c6a385a` | no browser header or footer (`@page margin:0`) |
      | `ff7e956`, `c62f96a` | the SF mark 1.5× inside the letterhead banner |
      | `17b2aba` (**A1**) | a blank **HSN prints an em-dash**, not the amber *add HSN* chip — on the tax invoice, the proforma, the purchase order, the RA bill and the merged RA |
      | `a22b26d` (**A4**) | **"This is a Computer Generated Document" is gone** from a sheet that carries a signature or a stamp. ⚠ **Inert until §5.1 is done** — with neither mark set every document prints byte-for-byte what it did |
      | `66759ef` (**B1**) | the product inquiry's title is **PRODUCT INQUIRY**, its meta label is **Inquiry No.** (the number is unchanged) and it asks for *our inquiry number* on the quotation |

      ⚠ **The §0 fifty-eighth block moves NO print golden at all** —
      `git diff 702a98e..83d4ef5 -- tests/test_print_golden.py` is empty, and
      `/projects/view` has no print route to leak the new charts onto.
      ⚠ **Nor do A2, A3, B2, B3 or B4.** For B2 and B4 that is measured
      rather than lucky and each has a test saying why: the picture column is
      drawn only where the library can offer something, and every pinned
      record is a BOQ **original**, so the revision-suffix strip is a no-op on
      all of them
- [ ] `/projects/view/<id>` opened by an **Owner** — the P&L's two new charts
      draw as inline SVG with a plain-text table under each. ⚠ **They were
      checked in headless Chromium at 1280 px and 390 px and add no horizontal
      overflow; the page does overflow at 390 px for reasons that predate this
      work** (ABOUT.md §7 **gap 91**, six panels across four modules). The owner
      works from a phone, so expect him to notice it
- [ ] `/ra/` opened — a Supply & Installation set raised at `/raboth/create`
      reads as a header row with its two legs indented under it
- [ ] The red persistence strip is **absent** (DEPLOY.md §11)
- [ ] **`/po/` opened** — it is headed *Product Inquiries*, the rail says the
      same, and the register's rows still link to `/po/view/<id>`
- [ ] **One product inquiry edited** — every field and every line is editable;
      **convert it, then try to edit it again** and confirm the control is
      greyed with its reason and that a typed `/po/edit/<id>` is refused
- [ ] **One BOQ revised** — the new record is `<root>/1` on the register and
      the **root** on the printed sheet, with `Revision 1` on its own row
- [ ] **`/settings` opened** — *Units of Measure* is there, under *Joint
      Measurement Sheet — columns*

---

## 7. What is deliberately NOT in this deploy

- **Approvals stay switched off** (`approval.LADDER_ON = False`) and the
  **product catalogue stays hidden** (`auth.HIDDEN_BLUEPRINTS`). Neither was
  touched. The client is to be reminded of both at go-live (DEPLOY.md §12)
- **No `/templates`, no `/static`, no CDN and no JavaScript chart library** were
  introduced. The two new charts are server-rendered inline SVG, and the
  fifty-ninth block's one new control is a `<select>`
- **`tools/clean_units.py` is NOT run** by this deploy (§4.1). The units
  dropdown works with every legacy string left exactly as it is
- **No rate on the Product Inquiry**, although A2's brief listed one: the
  document's rates are blank by design and the supplier fills them in. Manas's
  decision, recorded in the §0 fifty-ninth block
- **`quotation.py` and `product.py` were not edited** and no sixth narrow
  unfreeze was opened. Their unit fields therefore do not get B3's dropdown;
  the catalogue is hidden from everybody anyway
- **No print route was added to `/projects/view`**, so nothing about the P&L or
  its charts can reach paper
- **`docs/ACCESS_MATRIX.md` was regenerated** in the same commits that changed a
  permission, a role or a route classification, which
  `tests/test_access_matrix_doc.py` enforces. Nothing to do on the box

---

*Written 29 October 2026 and extended 30 October 2026 for the §0 **fifty-ninth**
block, on a cloud checkout with no MySQL and no access to production. Every
step above is for a human on the server. ⚠ **No database backup was taken
before any of this work because none was possible**; the backup in §2 is the
first one in this sequence and must be real.*
