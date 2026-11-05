# LABOUR_PL.md — why site labour does not reach the project P&L

> **Diagnosis pass, 5 November 2026.** Written before any code was changed, and
> committed on its own, so the reasoning can be read against the state of the
> tree it describes (`75720f4`). It is the Step 0 deliverable of the
> *"labour into project P&L"* pass — CLIENT_CHANGES.md §0, the
> **sixty-sixth** block.
>
> Every claim below is `file:line` against `75720f4`. Line numbers move; the
> function names do not, and each citation names the function as well.

---

## 0. The short answer

The P&L's labour row is **wired and correct**, and it reads **nothing**,
because the one field it joins on is **never written by the two paths that
create almost every marking in a real database**.

```
pnl.project_pnl()                     reads  markings_for_project(pid)
   └─ pnl.py:863                                attendance.py:616
                                                  └─ matches on  r["project_id"] == pid
                                                     and  A BLANK ID MATCHES NOTHING
                                                          (attendance.py:620-625)

who writes project_id ?
   /attendance/mark, /attendance/edit        attendance.resolve_project()   ✔ writes it
   /payroll/import  (the client's workbook)  payimport.commit()             ✔ but PER SITE
   tools/seed_demo_scenario.py               the demo's own markings        ✘ NEVER writes it
   every marking older than 30 Aug 2026      the field did not exist        ✘ has none
```

So the row is not broken arithmetic. It is an **empty join**, plus a second
defect that has nothing to do with the join at all: **an issued payslip is
not a cost anywhere in this application** (§4).

---

## 1. The path, end to end

### 1.1 Where a marking is born

Three writers, and only two of them know about a project.

| writer | `file:line` | writes `project_id`? |
|---|---|---|
| `/attendance/mark`, `/attendance/edit` (hand entry) | `attendance.resolve_project()` — `attendance.py:560` | **yes**, per marking, from the form's picker, filtered to the site |
| `/payroll/import` (the client's monthly sheet) | `payimport.commit()` — `payimport.py:401` | **yes, but one project for the WHOLE SITE** — see §2 |
| `tools/seed_demo_scenario.py` | `seed_demo_scenario.py:254-268` | **no. The key is absent from the record it builds** |

`attendance.import_marking()` (`attendance.py:856`) takes `project_fields` as
an argument and copies it onto the record. It does not derive one; it cannot —
it is handed one marking at a time and has no view of the sheet.

### 1.2 Where a marking becomes a site

`employee.resolve_site()` maps the sheet's free-text SITE to an address-book
id (`EMP.SITE_ADDRESS_FIELD`), exactly trimmed, never fuzzy-matched — an
unmatched string is left and marked `unmapped` (CLAUDE.md, 30 Aug 2026). That
half works, and `attendance.projects_on_site()` (`attendance.py:536`) turns a
site id into the projects filed at it.

### 1.3 Where a site becomes a project

`attendance.resolve_project()` (`attendance.py:560`) — the four outcomes in its
own docstring:

| posted | projects at that site | stored |
|---|---|---|
| one of them | any | that id, name snapshotted |
| not one of them | any | **dropped** |
| blank | 0 or 1 | no project, both keys cleared |
| blank | 2 or more | **refused** — a choice is required |

Note row 3: **a site carrying exactly one project still stores no project when
the form posts blank.** The form preselects it, so a human clicking through
gets it; nothing else does.

### 1.4 Where the project becomes money

`pnl.project_pnl()` — `pnl.py:862-866`:

```python
if include_labour:
    labour = dict(AT.labour_cost_of(AT.markings_for_project(pid)),
                  withheld=False)
```

and `attendance.markings_for_project()` — `attendance.py:616-631`:

```python
key = str(project_id or "").strip()
if not key:
    return []
return sorted((r for r in records().values()
               if str(r.get("project_id") or "").strip() == key), …)
```

A marking with no `project_id` is matched by **no** project id, which is the
correct and deliberate behaviour of that function (its own docstring explains
why a blank must not match a blank). The consequence is that it is also matched
by nothing else: the labour row prints `0.00` over `0 markings`, which reads as
*"no labour on this project"* rather than *"nobody told us whose labour it
was"*.

`pnl.waterfall_of()` (`pnl.py:683`) and the dashboard
(`dashboard.py:1894`) take the same dict, so all three displays inherit the
same zero from the same join.

### 1.5 The one place the money is visible

`projectview._site_labour()` (`projectview.py:245`) draws the Site Labour panel
in **two groups** — `projectview.py:168-179`:

```
Site Labour, group 1   r["project_id"] == id     somebody CHOSE this project
Site Labour, group 2   r["site_address_id"]      nobody chose anything
```

**Group 2 is the whole of the problem, rendered.** The panel shows the money.
The P&L, five hundred lines down the same file, does not — because
`_pnl_panel()` (`projectview.py:785`) takes `PNL.project_pnl()`, which only
ever sees group 1. One page, two figures, and the smaller one is the one in the
margin.

---

## 2. Defect A — the import decides the project PER SITE, not per worker

`payimport.site_choices()` (`payimport.py:343`) builds one dropdown entry per
**(site, project)** pair, and `payimport.commit()` (`payimport.py:415-419`)
resolves that dropdown **once per distinct sheet site**:

```python
mapping = {}
for i, site in enumerate(rec["sites"]):
    sf, pf, err = resolve_choice(form.get(f"site_{i}"))
    …
    mapping[site] = (sf, pf)
```

and then hands the same answer to **every row on that site**
(`payimport.py:431`):

```python
sf, pf = mapping.get(row["site"], ({}, {}))
```

Consequences, all three of them real on the client's own sheet:

1. **Jamnagar + Jamnagar Shed cannot be split.** Two live projects at one
   address. The operator picks one; every worker who was at either lands on
   the one picked. There is no shape in which half the sheet's Jamnagar rows go
   to the Shed.
2. **A multi-project site with no pick is a hard stop**, not a bucket:
   `resolve_choice()` returns `"several projects are at that site — choose one"`
   (`payimport.py:387`) and `commit()` abandons the whole import. The month
   does not go in at all, so the cheapest way past it is to pick *a* project —
   which is the silent mis-attribution the rest of this module is written to
   prevent.
3. **There is no way to say "this is not project labour".** Office and workshop
   days have to be given a site; a site with no project stores `project_id: ""`
   (`payimport.py:391-392`), which is **the same shape as a legacy marking** —
   `attendance.unattributed_at_site()` says so in terms
   (`attendance.py:635-648`): *"Absent means LEGACY, not 'no project', and this
   function does not claim to tell them apart."* So overhead labour sits for
   ever in the amber *"in no project's labour"* line
   (`attendance.off_project_labour()`, `attendance.py:671`) and nags about
   itself every time anybody opens a project.

## 3. Defect B — nothing assigns the backlog, and nothing lets a human fix one

`tools/backfill_marking_projects.py` exists (30 Aug 2026) and does the
unambiguous half correctly: one project at the site → link it; zero or two or
more → leave it and print it (`tools/backfill_marking_projects.py:22-32`). It
has **no notion of overhead**, it reports **markings** rather than
worker-months, and its own docstring sends the ambiguous rows to
`/attendance/edit/<id>` — **one marking at a time**. A month of one worker is
26 of those pages.

There is **no screen** that lists what is unassigned, and **no permission**
that governs assigning it. `auth.PERMISSIONS` carries `attendance.view` /
`attendance.edit` / `payroll.*` (`auth.py:503-513`) and nothing about
attribution.

## 4. Defect C — an issued payslip is not a cost

This one is independent of the join and would survive fixing it.

`payroll.snapshot()` (`payroll.py:380`) freezes `basic`, `ot`, `travel`,
`advance`, `loan_deduction`, `payable` onto the slip at issue, and
`payroll.issue()` (`payroll.py:457`) marks it `Issued` and never moves it
again. That snapshot is **what the client actually paid**.

Nothing outside `payroll.py` reads it:

```
$ grep -rn 'payslips\|slips()' *.py | grep -v '^payroll.py'
auth.py:512     "payroll.view":  …          # a permission label
auth.py:513     "payroll.edit":  …          # a permission label
db.py:82        "payslips",                 # persistence
db.py:277       "payslips": "payslips",     # persistence
payimport.py:517  for s in PAY.slips().values():   # the import's own blocker
store.py:49     "payslips": {},             # the collection's comment
```

So the P&L's labour row is **always the muster's own estimate** — `day_rate`
snapshotted on each marking × `DAY_SHARE` for its status, plus OT
(`attendance.cost_of()`, `attendance.py:450`). After the month is paid, that
estimate is never replaced by the figure on the slip, and the two differ
routinely: travel is on the slip and on no marking, and `other_allowance` and
the statutory heads are typed on the draft.

⚠ And the P&L has **no vocabulary for the difference**. `labour` carries
`total / markings / costed / refused / withheld` (`attendance.py:732`) — one
number, no split. A reader cannot tell a month that is paid from a month that
is guessed.

---

## 5. What is NOT wrong

Worth stating, because each of these looks like the bug and is not:

* **The arithmetic.** `cost_of()` prices a day correctly, `DAY_SHARE` handles
  half days and paid leave, the OT multiplier is a setting read in one place.
  `tests/test_attendance.py` walks the AST and refuses a literal in it.
* **The import graph.** `pnl.py` reaches the wage through
  `attendance.labour_cost_of()` and nothing else, and only four modules may
  import `attendance.py` at all (`tests/test_attendance.py:822-833`). Any fix
  has to keep the wage arithmetic inside `attendance.py`.
* **`off_project_labour()` and `pnl.untagged_cost()`.** The money is not
  *lost* today — both say, from opposite ends, that it is sitting outside every
  project. Nobody can act on either, which is Defect B, not a missing figure.
* **The site mapping.** Exact, never fuzzy, `unmapped` marked and reported.

---

## 6. What a fix has to do, in the order the defects force

1. **Write `project_id` per worker at import** (Defect A), with an overhead
   choice that is a *decision* rather than the absence of one, and a
   last-month default so the common case is one click.
2. **Give the backlog a screen and a permission** (Defect B), because the
   unambiguous half can be backfilled by a tool and the ambiguous half cannot.
3. **Replace the estimate with the slip where the slip exists** (Defect C),
   split across projects by the days each project got, and say on the face of
   the P&L which part is which.

Rulings 1–5 of 5 November 2026 (CLIENT_CHANGES.md §0, the sixty-sixth block)
are those three in that order.
