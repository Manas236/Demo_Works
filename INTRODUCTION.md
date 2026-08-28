# INTRODUCTION — read this first

> **This file owns:** what the system is, who it serves, the two chains, the
> document map, the reading order, the working protocol, and the forbidden list.
>
> **This file does not own:** the business domain (→ [DOMAIN.md](DOMAIN.md)),
> current phase state or the work queue (→ [STATE.md](STATE.md)), or anything
> architectural — module map, import directions, record shapes, per-page
> behaviour, conventions (→ [ABOUT.md](ABOUT.md)).
>
> Every fact in this repository has exactly one home. Where this file needs a
> fact it does not own, it links. If you find yourself about to restate a rule
> here that is written down elsewhere, link to it instead.

---

## 1. What this is

A **Flask quotation, schedule and billing system for Samruddhi Fire**, a
fire-protection **project contractor** in India. Not an AMC business and not an
extinguisher-servicing shop — their work is large project jobs, executed over
months and billed to a **main contractor** as the work is completed.

It is a **seller-side** application throughout. We write the schedule, we issue
the documents, we submit the claims. The customer sends *us* their purchase
order; we never issue one to a customer. The one place that inverts is
`purchase.py`, which is us buying from a vendor — see §3.

The stack is Flask, MySQL, roughly 12,000 lines of Python, no front-end build,
no ORM, no template files. That last part is not an accident and is not
technical debt; [ABOUT.md §1](ABOUT.md) explains why, and it is the single
thing most likely to break a page if you forget it.

---

## 2. Who it serves

| | |
|---|---|
| **The operator** | Samruddhi's own office staff — a small number of authenticated internal users. They author BOQs, enter site measurements as claims, and print what goes out. |
| **The recipient** | The **main contractor**, who receives the claim, certifies some or all of it, and pays. |
| **The end client** | The project owner. Named on the documents; never a user of this system. |

The operator is not an accountant and not a developer. A rule this system
enforces has to state its reason on the page, in words, at the moment it
fires — an error that says only "invalid" costs somebody an afternoon.

---

## 3. The two chains

There are two **sell-side** chains, and they are separate records end to end —
not two render modes of one document.

```
CHAIN 1   quotation ──► proforma invoice ──► tax invoice
          goods, offered and then invoiced in lots

CHAIN 2   BOQ ──► RA bill 1 ──► RA bill 2 ──► …
          a project, priced once and billed progressively as it is built
            │            │
            │            └──► receipt, receipt, …
            │                 money actually received against a bill
            │
            ├──► draft PO, draft PO, …    sent to a supplier to be priced
            └──► challan, challan, …      goods leaving the yard

BUY SIDE  purchase order ──► [vendor lifecycle]
          a separate pipeline; never links to a proforma or a tax invoice
```

⚠ **The draft PO and the delivery challan hang off the BOQ, not off an RA
bill.** A challan in particular sits *beside* the bill and is deliberately not
reconciled with it: one records goods moved, the other money claimed, and they
legitimately disagree at any moment. [ABOUT.md §5](ABOUT.md) (`/dc`) and §7
gap 19.

**Chain 1** sells things. A quotation offers goods at a price; a proforma
requests money against it; a tax invoice records the supply. Each link freezes a
copy of the line items at the moment it is issued.

**Chain 2** bills work. A **BOQ** — bill of quantities — is the priced schedule
of one project, one to two hundred lines. An **RA bill** — running account — is
a claim against that schedule: how much of each approved line was executed this
period. There are typically nine or more against one BOQ.

They are separate chains because the unit of progress differs. Chain 1's unit is
a document; Chain 2's is **a quantity on a line**, and no field on a quotation
can carry that. [DOMAIN.md](DOMAIN.md) is the full explanation and is the most
important file in this set — read it before you touch `boq.py` or `ra.py`.

**Your work is in Chain 2.** Chain 1 is older code, it is where the two
forbidden files live (§7), and nothing you are asked to build needs to reach
into it.

The two chains do share a toolkit — the A4 sheet, the money formatters, the
stylesheet — imported strictly one way. [ABOUT.md §2b](ABOUT.md) has the arrows,
and [tests/test_import_directions.py](tests/test_import_directions.py) fails if
you reverse one.

---

## 4. The document map — where each fact lives

Read in this order. Do not skip ABOUT.md because it is long; skim §5 by section
heading and read the rest.

| # | File | Owns | Explicitly does not own |
|---|---|---|---|
| 1 | **INTRODUCTION.md** (this) | Orientation, doc map, working protocol, forbidden list | Domain rules, phase state, architecture |
| 2 | **[DOMAIN.md](DOMAIN.md)** | The business, in plain language. BOQ structure, item numbering, areas, the supply/installation split, RA billing, legs, cumulative claims, certification, the tax-invoice requirement, and the imperfect-data principle | Anything about code |
| 3 | **[STATE.md](STATE.md)** | What each Phase 4 step shipped, what is open, what is next, in order | Why a rule exists — that is DOMAIN.md |
| 4 | **[ABOUT.md](ABOUT.md)** | **The architecture.** Module map, import graph, every record shape, persistence, per-page behaviour, branding, code-level gaps, conventions | The business reasoning; the forward queue |
| 5 | **[CLAUDE.md](CLAUDE.md)** | The three fast facts that stop you breaking a page before you have read anything | Everything else — it points at ABOUT.md |
| 6 | **[PHASE4_RA_DESIGN.md](PHASE4_RA_DESIGN.md)** | The approved RA billing design and the **decision record** — what was settled on 2026-08-05, what was amended, and what was left open on purpose | Current state — that is STATE.md |
| 7 | **[CLIENT_CHANGES.md](CLIENT_CHANGES.md)** | What the **client** asked for, one row per request, with its client-facing status; the standing approach those items are built against; the open questions we are waiting on them to answer | Gaps we found ourselves; the ordered queue; anything architectural |
| 8 | **[CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md)** | **Phase 3 scope only** — the 19 August 2026 meeting, as 3A / 3B / 3C with the build order and the invariants each item has to hold. Read it before touching anything about users, approvals, attachments, measurement, the merged RA or labour cost | Phase 2 and earlier — that is CLIENT_CHANGES.md; permission to build any of it |
| 9 | **[SOURCE_DOCUMENTS.md](SOURCE_DOCUMENTS.md)** | What the client's own 18 source documents actually contain — structure, conventions and defects — and what that evidence does to DOMAIN.md's claims. Read it before asserting how the client's paperwork behaves; the documents themselves are gitignored | The domain model, the code facts, the work queue; every finding is OPEN and none is actioned |
| 10 | **[fixtures/README.md](fixtures/README.md)** | The two client workbooks: what they are, where to put them, what happens without them | — |
| 11 | **[PROGRESS.md](PROGRESS.md)** | **Phase 3 build status**, one row per CLIENT_CHANGES-2.md item — BUILT / PARTIAL / NOT STARTED / BLOCKED, each with the `file:line`, route or test name it was established from, plus the blockers and the code-vs-docs drift found while establishing them. Regenerated from code; a pass that changes a Phase 3 item's build state updates it in the same commit | What the items *are* — that is CLIENT_CHANGES-2.md; permission to build any of them; anything about Phase 2 or Phase 4 |
| 12 | **[docs/ACCESS_MATRIX.md](docs/ACCESS_MATRIX.md)** | **Who can do what** — the 7 roles × 61 permissions grid, a plain-English paragraph per role, and a mark on **every cell** saying whether it comes from CLIENT_CHANGES-2.md or is our derivation. **Generated** by [tools/dump_access_matrix.py](tools/dump_access_matrix.py) from the live catalogue and never hand-edited; `tests/test_access_matrix_doc.py` fails if it drifts. Written to be walked through with the client | The reason any permission is where it is — that is a conversation still to be had; anything about how the gate works (→ ABOUT.md §2g) |

### The boundary that is easiest to get wrong

**ABOUT.md §7, STATE.md and CLIENT_CHANGES.md all list things that are not
done.** Three lists, three different questions:

- **ABOUT.md §7** owns gaps in **code that already exists** — the missing
  product edit route, the escaping holes, the absence of e-invoicing. Things
  *we* found.
- **STATE.md** owns **work not yet started** — the ordered queue, and
  requirements learned from the client that have no code behind them at all.
- **CLIENT_CHANGES.md** owns **what the client asked for** and where each
  request stands. Things *they* asked for.

So: ABOUT.md §7.1 owns *which dependencies this app needs*. STATE.md owns *that
writing `requirements.txt` is an immediate task*. None of the three restates
another; where an item belongs on two of them, each entry answers its own
question and links to the other.

⚠ **CLIENT_CHANGES.md carries a rule the other two do not.** It is a **status
record, not a work queue**: an unbuilt item listed there is a record of a
conversation, not a task, and anything on it that is **new scope priced into
Phase 2** is gated until the client's quotation is signed. **Defect and
reachability fixes against scope already sold are exempt** — that is what
ABOUT.md §7 mostly is, so §7 is not gated by this. Read CLIENT_CHANGES.md §0
before acting on anything in it. The queue is STATE.md.

### A note on SAMRUDHI_SPEC.md

`SAMRUDHI_SPEC.md` is **untracked** in the working tree and is the draft this
document set was written from. Its §2 became DOMAIN.md, its §3 and §7 became
STATE.md, its §0 and §1 became this file plus ABOUT.md. It is superseded and
should be deleted rather than maintained — keeping it is four homes for facts
that now have one each. **Do not read it as authoritative and do not update it.**

### Finding your way around ABOUT.md

It is 4,100-odd lines. Section headings, so you can jump:

| § | What is there |
|---|---|
| 1 | What the app is · **the f-string / no-`/templates` rule** — read this one |
| 2 | Module map, line counts, and the full import-direction graph |
| 2b | **The BOQ chain** — `boq.py` and `ra.py`, and what each may import |
| 2c | **Receipts** — `receipt.py`, and why the balance arithmetic lives upstream in `ra.py` |
| 2d | **`docsheet.py`** — the one printed A4 sheet, why it is a leaf, and how that keeps `ra.py` and `invoice.py` apart |
| 2e | **`boqpick.py`** — the one BOQ line picker, why it is also a leaf, and how that keeps `po_draft.py` and `challan.py` apart |
| 2g | **`auth.py`** — the fourth bottom-of-graph module, and the only one that renders. Why access control has to sit under `dashboard.py`, the two page shells, and **why the gate is a central registry rather than a decorator** |
| 3 | **Every record shape**, with the properties each shape exists to guarantee |
| 4 | Persistence — how `db.py` snapshots and diffs, and how failure surfaces |
| 5 | Page by page, route by route. `/boq` and `/ra` are the ones you need; `/client` and `/po` are the newest |
| 6 | Branding, the settings override mechanism, the chart palette |
| 7 | **Known gaps in existing code** — read before proposing a fix, it is probably here |
| 8 | Two dead files. `integration.py` and `product_view_additions.py` — do not implement against either |
| 9 | Conventions for new code |

---

## 5. The working protocol — mandatory

This is a standing rule set, not a suggestion, and it applies to every task on
this repository.

### 5.1 Plan, then pause

Before writing any code, state **what you intend to change, which files, and
which tests will prove it**. Then stop and wait for approval.

Do not combine planning and execution in one action. A plan that arrives
alongside the diff is not a plan — it is a notification.

### 5.2 Stop and report after each numbered step

Work is broken into numbered steps for a reason. Finish one, report what
happened, wait. **Do not chain steps**, even when the next one looks obvious and
small.

### 5.3 Back up the database before anything that writes to it

```bash
python tools/backup_db.py --label <what-you-are-about-to-do>
```

It reads the same `.env` the app does, so it always dumps the database the app
is actually using; it writes to `backups/`, and it refuses to call a dump under
100 bytes a backup ([tools/backup_db.py:51-82](tools/backup_db.py#L51-L82)).

"Anything that writes to it" includes **starting the app**: `db.sync()` runs
from `teardown_request` on every request ([ABOUT.md §4](ABOUT.md)), so a single
page load can persist a change. Back up first, then run.

### 5.4 Ask before anything destructive

Deleting records, dropping or altering a column, rewriting stored JSON, running
a migration, force-pushing — every one of these needs explicit approval before
you start, backup or no backup.

### 5.5 Never reduce the test count

The baseline is **1,367 passed / 1 skipped** on 29 August 2026, verified by
running the suite in this configuration: openpyxl **absent**, both client workbooks **absent**, global `C:\Program Files\Python310` (CPython 3.10.11), **no `.venv`**.

*(The 29 August pass opened Phase 3C and added **92**: `tests/test_employee.py`
(34) and `tests/test_po_extra_lines.py` (33) are new, and
`tests/test_import_directions.py` went 231 → 256 for the two new modules' import
arrows. It built **C4**, the employee master, and **extra free-text
purchase-order lines** — the latter ⚠ **not one of CC-2's twenty items** and
priced in neither quotation; see PROGRESS.md §4a.)*

*(The 28 August pass ([STATE.md §1.18](STATE.md)) closed Phase 3A and added
**50**: `tests/test_po_charges.py` (25) and `tests/test_ra_edit_delete.py` (11)
are new, `tests/test_po_rate_edit.py` went 21 → 32 and
`tests/test_receipt_write_off.py` 21 → 24. **Five existing tests were
deliberately retargeted in that pass and none was deleted** — four pinned A1's
Draft-only narrowing, which was lifted, and one was a tripwire written to fail
when its defect was fixed. Every one keeps its old assertion verbatim in a
comment; see §5.5's rule below on what makes that legitimate. The 27 August
day's four passes took it **1,058 → 1,062 → 1,151 → 1,225**. The last of
them is the **Phase 3A document** pass ([STATE.md §1.17](STATE.md)), which added
**74** in four files: `tests/test_po_discount.py` (22),
`tests/test_po_rate_edit.py` (21), `tests/test_receipt_write_off.py` (21) and
`tests/test_client_outstanding.py` (10). Before it, the escalation / sign-out /
navigation pass added 89 — `tests/test_privilege_escalation.py` (17),
`tests/test_nav_user_chip.py` (23), `tests/test_nav_visibility.py` (49) — and
break-glass recovery added 4 over `tools/set_password.py`. Earlier: **986 / 1**
on 26 August 2026, **923 / 1** on 23 August, **838 / 1** on 16 August, all in
the same configuration. Every figure was re-measured at the start of the pass
that moved it rather than quoted, and every one matched.)*

⚠ **The purchase-order golden was re-baselined TWICE on 28 August 2026, by the
pass that closed Phase 3A — and both times the movement was the work.** It moved
**+1,021 bytes** for **A1** (939 of `.po-reprice` stylesheet, plus an 82-byte
`Reprice` anchor that the **Issued** golden order qualifies for now the
Draft-only narrowing is lifted) and **+937 bytes** for **A3** (all of it
`.chg-*` stylesheet for the charge repeater). **Both moved the `head` block and
nothing else** — and `head` runs from `<head>` to the letterhead, so it carries
the stylesheet, the nav and the screen action bar, not just the `<head>`
element. `letterhead`, `foot-strip`, `doc-box`, `party`, `items` and `signature`
are byte-identical through both. **Not one figure on the printed sheet moved**:
the golden order carries no charges and has never been repriced, so no charge
row and no `Rate changes` panel render and `taxable_value` falls back to
`subtotal`. The other six goldens did not move. Every byte is decomposed in the
comment above the digests in `tests/test_print_golden.py`.

⚠ **One print golden was re-baselined on 27 August 2026 by the Phase 3A document
pass, and this is the second circumstance in which that is allowed.** The purchase
order moved **+942 bytes**, in two of its seven blocks, because
CLIENT_CHANGES-2.md **A2** added a discount column to the buy sheet — head +721
of CSS, items +221 of cells. **The change was the work, not a side effect**, and
every byte is decomposed in the comment above the digests in
`tests/test_print_golden.py`. **No figure on the sheet moved**: the golden PO
carries no discount, so its new column prints an em dash and its Order Value is
unchanged at 307,508.00. The quotation, proforma, tax invoice, RA bill, delivery
challan and `/po/create` goldens did **not** move — that separation is what
`docsheet.BUY_COLUMNS` and the `.c-disc` rule's placement in `PURCHASE_STYLES`
exist to hold.

*(The first circumstance, still the more common one: **five goldens were
re-baselined earlier on 27 August 2026**, by +8 bytes each and in two blocks
only — the letterhead and the footer. The whole difference was the `&` in the
company tagline now being written `&amp;`, which a browser draws identically;
no rendered figure moved there either.)*

**In both cases the rule is the same and it is not "the suite is red, update
the number":** you may re-baseline only when you can say **which field moved,
by how many bytes, and why** — in writing, beside the digest, in the same
commit as the change.

**The supported configuration is measured too:** the repo's `.venv` (CPython
3.10.11, **openpyxl 3.1.5 present**, both workbooks absent) reports **1,226 passed
/ 3 skipped**, measured 27 August 2026 against the same commit. It read
**1,152 / 3** against the pre-pass code, measured the same day.

*(⚠ **This paragraph used to say that row was "derived". It was wrong.**
ABOUT.md §1 has recorded row 2 as **measured on 23 August 2026** since that
date; this file went on describing it as derived, which is the same
documentation drift §5.5 exists to warn about, pointing the wrong way. Corrected
26 August 2026 after re-running it and getting ABOUT.md's figure back.)*

The +1 pass and +2 skips over the global figure are the whole of the openpyxl
difference: `tests/test_fixtures.py` holds its 4 tests behind a **module-level**
`pytest.importorskip("openpyxl")`. Without openpyxl the module fails at
**collection** and pytest prints **1 skipped** for all four; with it the module
collects and the individual skips appear. One skip standing for four uncollected
tests is the thing most often got wrong about this suite.

⚠ **The third configuration — *openpyxl present, workbooks present* — has never
been measured**, and [ABOUT.md §1](ABOUT.md) row 1 marks it **unknown** rather
than guessing. This box has openpyxl but neither `sify_boq.xlsx` nor
`annexure.xlsx`. A count nobody ran is a claim, not a result: if you are on a box
that has the workbooks, run it and put the measured figure in.

**Always state which of the three you ran.** A count on its own is not a
result: the three move independently, and one pass reported "607 to 630" and
"638 passing" without naming a configuration for either.
[ABOUT.md §1](ABOUT.md) has the table and explains why the two mechanisms are
different — a module-level `importorskip` reports **one** skip however many
tests sit behind it, which is the thing most often got wrong about this suite.

If your first run reports something outside those three, stop and say so before
making a change.

Run before and after every change, and **report both numbers**:

```bash
.venv\Scripts\python -m pytest -q      # Windows
```

If a test is genuinely wrong, **say why and wait**. Deleting or weakening a failing test is never the fix — several
tests in this suite are deliberate controls that exist to prove another test
can actually fail, and they look redundant until you understand what they pin.

### 5.6 When code and a document disagree, the code is right

These documents record decisions and constraints. They can go stale. Where a
document says a function behaves one way and the function behaves another,
**the code is authoritative — report the drift, do not edit the code to match
the prose.**

The exception is a requirement explicitly marked as *not yet implemented*.
Those are written down precisely because the code does not do them yet.

### 5.7 Environment

`requirements.txt` **is committed and pinned**, and a **`.venv` is the
supported way to run this repo** — not a system interpreter, which the pins
would downgrade. **Supported: CPython 3.10 to 3.14**, last verified on 3.14.3
(Windows). The dependency *set* is derived from the actual imports rather than
a `pip freeze`; [ABOUT.md §1](ABOUT.md) has the cold-start sequence and
[ABOUT.md §7.1](ABOUT.md) owns the dependency list.

---

## 6. Three things about this codebase that will bite you first

All three are covered fully in ABOUT.md. They are repeated here — as pointers,
not explanations — only because they are what breaks on day one.

1. **HTML lives in Python f-strings**, so every literal `{` and `}` in embedded
   CSS or JavaScript must be **doubled** (`{{` / `}}`). This is the single most
   common way to break a page here. [ABOUT.md §1](ABOUT.md).
2. **`render_template_string` is gone from every module** and must not be
   reintroduced anywhere. A fully-interpolated string parsed a second time
   executes any `{{ … }}` that came from user input — and did, until
   27 August 2026: a product named `{{ config['SECRET_KEY'] }}` printed this
   application's signing key. [ABOUT.md §7.9d](ABOUT.md).
3. **Escape every user-supplied value where you interpolate it**, with `P.esc`.
   Not in a response filter — that would double-escape the deliberate markup and
   mangle the print pages. Never escape a money or quantity format, and never
   escape a value a helper has already escaped. [ABOUT.md §9](ABOUT.md) has the
   full rule and [ABOUT.md §7.7](ABOUT.md) has the sinks that are easy to miss.

---

## 7. Files you must not refactor

- **`product.py`**
- **`quotation.py`**

Both belong to Chain 1, the older sell chain. Both are **frozen against
refactor and feature work**, and both are **out of scope for you**. Do not tidy
them, do not restructure them, do not port a nicer pattern across from
`spec.py`, and do not build the missing product edit route
([ABOUT.md §7.2](ABOUT.md)) in one of them. Editing either expands the blast
radius into code that has no test coverage for your changes, and the deferral is
a decision that has already been taken — it is not an oversight you have
spotted.

### The one exception, and what it does not license

**Narrow security fixes and route-method fixes are permitted**, and must be
called out in the commit that makes them and in ABOUT.md. Two have now happened:

- `9d060ee` (12 August 2026) closed a GET that destroyed a product.
- **27 August 2026** escaped the unescaped output and removed the second Jinja
  parse from both files. That was the item CLIENT_CHANGES-2.md's own "Security
  items promoted by this phase" names, and it says in as many words that the
  freeze "explicitly permits" it.

⚠ **This section used to say these files "carry known unescaped output".** They
no longer do — [ABOUT.md §7.7 and §7.9d](ABOUT.md) are closed. **The
prohibition is unchanged by that**, because it was never really about the
escaping: it is about not taking on a refactor of untested code in the older
chain. A security fix being allowed once, and then twice, is not the freeze
being lifted.

⚠ **And do not read "the two files with the escaping problem" as the boundary
of an escaping problem.** The 27 August enumeration found the same defect in
fifteen other files — most importantly the company identity from `/settings`,
which printed raw on every document's letterhead. If you are looking for a sink,
sweep the routes; do not read these two files and stop.

**Importing from them is fine and expected** — see below.

**Importing from them is fine and expected.** `ra.py` imports
`QUOTATION_STYLES` and `_inr` from `quotation.py`
([ra.py:69](ra.py#L69)) so that the RA form is the same form as the BOQ form.
The prohibition is on *editing* those two files, not on depending on them.

**One import is prohibited as well: `quotation._tax_lines()`.** That is a
separate rule with its own reason, and it is **not** affected by §8. It is
document-total arithmetic branching on a `tax_type` it is handed
([quotation.py:79-98](quotation.py#L79-L98)) — it does not decide which tax
head applies, it has no per-line concept, and it lives in a file you may not
edit. `ra.py` grows its own. [DOMAIN.md](DOMAIN.md) carries the full reason.

---

## 8. One rule in this codebase is now known to be wrong

`ra.py` currently asserts, in code and in a test that reads its AST, that **an RA
bill is not a tax invoice**. The client's real as-submitted bill arrived on
8 August 2026 and is headed *Tax Invoice*.

That assertion must be **inverted, not deleted** — and it is **not yet
implemented**. Do not act on this section on your own initiative.

**Inverting it does not unlock `quotation._tax_lines()`.** That prohibition
(§7) rests on its own reasons and survives this change untouched. The
assertion being inverted is the one about *what kind of document an RA bill
is*; several of the absences the same test pins — e-invoicing among them —
stay asserted. It is one test becoming three, not one flipped boolean.

- The requirement, and everything the client's real document carries, is in
  [DOMAIN.md](DOMAIN.md).
- Its position in the work queue is in [STATE.md](STATE.md).

---

## 9. The principle underneath all of it

**The client's own data is imperfect, and it must survive rather than be
repaired.** Their real documents contain a duplicated item number, raw Excel
date serials where dates belong, and a supplier sheet carrying the wrong state's
GSTIN. Every guard in this system **blocks, warns or flags — it never silently
corrects.**

An agent trying to be helpful by cleaning up the client's data is the specific
failure mode this document set exists to prevent. [DOMAIN.md](DOMAIN.md) states
it in full, with what each of those three defects actually cost.

---

## 10. Where you are

**Branch:** `antigravity-dev`, cut from `feature/boq-ra` at `fe629d5`.

`Quote.html` is untracked in the working tree and would ride along in a
`git add .`. Handling it is an open item in [STATE.md](STATE.md).

Now read [DOMAIN.md](DOMAIN.md).
