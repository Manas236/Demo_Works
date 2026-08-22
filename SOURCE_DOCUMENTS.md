# SOURCE DOCUMENTS — evidence from the client's own paperwork

> **Pass date:** 2026-08-22 · **Batch received:** 2026-08-22 (all 18 files carry
> that modification date) · **Branch:** `antigravity-dev` at `fe6757d`
>
> **This file owns:** what the client's real source documents actually contain —
> structure, conventions, defects — and what that evidence does to the claims in
> [DOMAIN.md](DOMAIN.md). It is a **findings document**, not a model and not a
> change list.
>
> **This file does not own:** the domain model ([DOMAIN.md](DOMAIN.md)), the
> code facts ([ABOUT.md](ABOUT.md)), the work queue ([STATE.md](STATE.md)), or
> the client's requested changes ([CLIENT_CHANGES.md](CLIENT_CHANGES.md)).
>
> **Nothing here has been actioned.** Every finding is marked **OPEN**. Manas
> rules on them; a later pass amends DOMAIN.md. This pass deliberately did not.

## Two rules this file was written under

**SELF-CONTAINED.** The documents themselves are gitignored (`client_docs/`) and
will not be on anyone else's machine. Column layouts and conventions are
therefore described in enough detail to be useful with the workbooks absent. The
sha256 inventory below is what makes provenance checkable later.

**REDACTED.** These are real customers' priced schedules. This file records
**structure and findings, not data**. A figure appears only where the figure *is*
the finding. There are no rate tables, no party lists and no GSTIN dumps here.

---

## 1. Inventory

18 files: **16 workbooks + 2 PDFs**. All 18 were read successfully. Nothing was
unreadable.

| # | File | Type | sha256 | Bytes |
|---|---|---|---|---|
| 1 | `ATTENDANCE_SHEET.xlsx` | xlsx | `918bdbecce285205be7d235021f2fca247887c75c6f9dc99363bd9515c45a9c6` | 24,844 |
| 2 | `Abhilasha.xlsx` | xlsx | `26edc2c02f32a166d0e0ba9e9367c92d8783fc136be7e389ed940c63d1ee434a` | 67,066 |
| 3 | `BOQ_Kandivali.xls` | xls | `47040c4b29c091fd63f88c74c3ee6d65fc789dcfcf4effe4ec93ce1cc296f1e7` | 101,376 |
| 4 | `BOQ_New_(Recovered).xls` | xls | `556aa2c035ed0d02e830b8cc6e20829ae20391244b5d8aa24a79cedb3ac7bd43` | 58,880 |
| 5 | `Bhaveshwar_Callista_roadpali.xlsx` | xlsx | `fe45be17f631f896bd5d1eadc6bbe07b077fb162406f201cf5c280244960acac` | 11,360 |
| 6 | `DC-SF.xlsx` | xlsx | `2f560f32f99fce21f1e9d5542ca47345b714e93669e0b5869b3c5f485e4bd3e0` | 72,362 |
| 7 | `Kalyan_Site.xlsx` | xlsx | `62af5db9f2a1e2a9f0f1c0677f6ef9118be164c8432dc4a94705cf012ac9a7ac` | 74,806 |
| 8 | `Khargar_38th_Floors.xls` | xls | `bae882a65799286279f8dd9a0a28e9e906a2d7f9a14992007ce9c9cb196af8c3` | 52,224 |
| 9 | `Measurement_Sheet_updated.xlsx` | xlsx | `3f170470aeff99f31d6efb8bbebdf09ef6933af74f6de56be8be8c5cfea47b20` | 30,253 |
| 10 | `Measurement_sheet2.pdf` | pdf | `36542ccf453fc226d16d537505a5e953523453c2de5bd9a546395ebabcdb1d1d` | 422,960 |
| 11 | `Measurement_sheet3.pdf` | pdf | `abf72a2e43b304ddea420c337afea56a2b809a62ce0959eed0dc88724ce63133` | 440,256 |
| 12 | `Mundra_Gujrat_Fire_fighting.xlsx` | xlsx | `69cc15b12e0d4e8322a33fc3d3bd25edfda278cadb5bd09ee9f87f409acbcc5c` | 24,458 |
| 13 | `New_Qoute.xlsx` | xlsx | `a1b28e57fae3a1262b974f92ab3aa0ddd6e13698558ce28871fc4cbf9a52170d` | 20,017 |
| 14 | `Quotation_for_Ground+9th_Floor.xlsx` | xlsx | `6cf450f94360e98be9d63e752593fd167d68519f6c7f4a953020135784d90176` | 21,133 |
| 15 | `RD_fire.xlsx` | xlsx | `343b7613490433f2aa15870b69e6e1c1a8807db000e6d37af1d75c71e7f2d6c1` | 451,437 |
| 16 | `Skyline.xlsx` | xlsx | `aa7c092f3113b3f3887f570d4fba4325fbe972080970f3846ebe7a4e74bb3a85` | 36,186 |
| 17 | `Walkeshwar_Blank_BOQ_Fire_Hydrant_&_Sprinkler.xls` | xls | `6ac97ddc84babe44e566d9508c30e2cc07beb1dd0eb466ffaedcb08b652cdbfc` | 332,800 |
| 18 | `fire_e_fighting-Turbhe.xlsx` | xlsx | `b7e8d97ab5d9f82d1c10d762a9f64674c4c6adfea439b00381cea2c661d1eff9` | 33,821 |

**File count vs what was stated.** "16 Excel workbooks + 2 PDFs" is exactly
right. "15 docs" is wrong as a file count. But **neither number describes the
document count**, in both directions:

- **Downward.** `Measurement_sheet2.pdf` and `Measurement_sheet3.pdf` are **not
  independent documents**. They are print-outs of `Measurement_Sheet_updated.xlsx`
  tabs `Sheet2` and `Sheet3` — same dates, same rows, same values. Two of the 18
  files carry no information the other 16 do not.
- **Upward.** Several workbooks carry several documents. `RD_fire.xlsx` holds a
  cost abstract, a BOQ and five takeoffs. `Kalyan_Site.xlsx` holds **two
  different companies'** documents.

Counting logical documents rather than files: **16 distinct source files,
carrying ~45 sheets, of which roughly 22 are priced schedules or documents and
the rest are takeoffs, approved-make lists and covers.**

---

## 2. Categorisation

| Classification | Files |
|---|---|
| **BOQ (priced)** | `Khargar_38th_Floors.xls`, `Mundra_Gujrat_Fire_fighting.xlsx`, `Kalyan_Site.xlsx` (BOQ tab), `RD_fire.xlsx` (BOQ region), `Abhilasha.xlsx`, `BOQ_Kandivali.xls` |
| **BOQ (blank / unpriced template)** | `fire_e_fighting-Turbhe.xlsx`, `Walkeshwar_Blank_BOQ_…xls` |
| **Quotation** | `BOQ_New_(Recovered).xls`, `New_Qoute.xlsx`, `Quotation_for_Ground+9th_Floor.xlsx`, `Skyline.xlsx`, `Kalyan_Site.xlsx` (Sheet1 cover) |
| **Measurement sheet** | `Measurement_Sheet_updated.xlsx` (3 documents), `Measurement_sheet2.pdf`, `Measurement_sheet3.pdf` |
| **Delivery Challan** | `DC-SF.xlsx` |
| **Attendance / labour** | `ATTENDANCE_SHEET.xlsx` |
| **Rate list (purchase side)** | `Bhaveshwar_Callista_roadpali.xlsx` |
| **Quantity takeoff** (working material, *not* BOQs) | 8 hidden sheets in `Walkeshwar`, 5 `Qty.-*` sheets in `RD_fire.xlsx`, `Kalyan_Site.xlsx` "Measurment sheet" tab, `Measurement_Sheet_updated.xlsx` Sheet1 |
| **RA bill (supply)** | **NONE** |
| **RA bill (installation)** | **NONE** |
| **Tax Invoice** | **NONE** |
| **Proforma** | **NONE** |
| **Purchase Order** | **NONE** |

> **The single most consequential fact in this batch: it contains no RA bill, no
> tax invoice and no purchase order.** See §7.5.

---

## 3. Per-document records

### 3.1 `Measurement_Sheet_updated.xlsx` — three documents, and the batch's most valuable find

Three tabs, three *different* documents. **OPEN.**

**Sheet1 — "JOINT MEASUREMENT SHEET" (blank pro-forma).**
This is the BoQ → Measurement → RA-Installation bridge document that Phase 3 has
had no sample of.

- Header block, label/value pairs down column A: `SITE`, `SYSTEM`, `MATERIAL`,
  `DIA METER`, `AREA`. Seller name and address sit in column L of the same rows.
- **Two-row banded header** at r7/r8. r7 declares locations column + nine
  diameter columns (`25 NB`…`200 NB`) + `SUPPORTS` + `SPRINKLER` + `REMARKS`;
  r8 carries the sub-headers `MSA (kgs)` under SUPPORTS and `PENDANT` / `UPRIGHT`
  under SPRINKLER. So SPRINKLER spans two physical columns.
- **Locations are ROWS** — a fixed vocabulary: `H1`, `SH 1`, `B1`–`B7`,
  `Hosereel`, `Hose Box`, `Hydrant`, `Air Release`, `Air Vessel`, `RRL Hose`,
  `Branch Pipe`, `4 Way`. Sizes are COLUMNS.
- `TOTAL` row at r36. Sheet is **entirely unfilled** — every total is 0.
- **A two-party signature block**: `NAME / DESIGNATION / SIGNATURE / DATE` in
  column A under the seller's name, and `NAME / DESIGN. / SIGN. / DATE` again in
  column L. **That is what "JOINT" means — both the subcontractor and the main
  contractor sign the measurement.** Nothing in the system models a
  counter-signature.
- **DEFECT — the total row is off by one against its header.** Headers occupy
  C…N; the TOTAL row writes a value into unheaded column **B**, and writes **no
  total for column C (`25 NB`) or column L (`SUPPORTS / MSA kgs`)**. Surface,
  do not fix.

**Sheet2 and Sheet3 — two filled measurement sheets** (dated 15/07/2026 and
17/08/2026). These are the two PDFs.

- Columns: `Location | Pipe Dia` (Sheet3: `Dia`) `| Quantity | Total | Unit`.
- **No rates. No amounts.** Pure measurement.
- **No item numbers of any kind.** There is no column that could join to a BOQ
  `item_no`, and no `line_id` equivalent. The only join key to a BOQ line is the
  natural key *(description text + diameter + unit)*.
- **THE QUANTITY COLUMN IS A TEXT ARITHMETIC EXPRESSION.** `9.3+1.5+6` with
  `16.8` in Total; `2.9+12+2.9+2.9+12+2.9` → `35.6`; and multiplication in a
  second notation, `1.2X3` → `3.6`, `2.6X2` → `5.2`, `1.9X2` → `3.8`. A capital
  `X`, not `*`. This is how a site engineer records each measured run
  separately and lets the sheet foot them. **Any importer reading this column
  gets a string, not a float**, and the two operators are inconsistent.
- Section structure is by **bare label rows with a trailing dash** —
  `PUMP ROOM -`, `Vessel -`, `Above Tank -`, `Drawout Connection -` — and by
  un-suffixed location rows (`Pumproom to outside ring`). Not A/B/C.
- Units are mixed within one sheet: `Mtr`, `Nos`, `Kg`.
- **DEFECT — a unit that contradicts its own row.** A `Pipe 150NB` row whose
  quantity is a length expression (`3.3+1.5+0.6` → `5.4`) carries unit **`Nos`**;
  the identical construction two rows later carries `Mtr`. Surface, do not fix.
- Dates are document-level free text (`Date : 15/07/2026`), `dd/mm/yyyy`, in a
  cell of their own — **not** a spreadsheet date and not a serial.

### 3.2 `DC-SF.xlsx` — Delivery Challan (the only one)

One sheet, one document. Real, issued, numbered. **OPEN.**

- Party block is **three-way and asymmetric**: seller (office address, contact,
  GSTIN) on the left; on the right a **`Consignee Name`** *and* a separate
  **`Consignee Address`** — **and they are different companies.** The consignee
  named is one firm; the address given is a *different* firm's premises at
  Mohali. See §6.1 — this contradicts DOMAIN.md §5.1.
- Reference block: `Challan No`, `Challan Date`, `Dispatch Mode`,
  `PO No.`, `PO Date`, `Dispatch to`, `Phone No`, **`Vehicle No.`**.
- **`Challan No` is a bare running integer** — no prefix, no financial-year
  segment, no per-party series. (The system's references are `fy_ref`-shaped.)
- **The `PO No.` field holds a Work Order number**, formatted `WO/nnn/yy-yy`, so
  the field is really "the main contractor's reference, whatever he calls it".
- Line columns: `Sr.No. | Description | HSN / SAC Code | Quantity | Unit`.
  **No rate column, no amount column, no tax.**
- **HSN/SAC is carried per line** on the challan.
- Foot: a certification sentence, `For <seller>`, `Name & Signature of Receiver`
  and `Authorized Signatory` — again a two-party signature.
- Seller GSTIN state code is **27 (Maharashtra)** and the dispatch destination is
  **Mohali (Punjab)**. An out-of-state movement — but a challan carries no tax,
  so it does not answer §7.3.
- **DEFECT — mojibake.** Two cells of the seller's own address block have
  lost a punctuation character to an encoding round-trip — a hyphen in one
  and an en-dash in the other, both rendering as a replacement glyph. The
  address values are not reproduced here.

### 3.3 `ATTENDANCE_SHEET.xlsx` — labour, and the site evidence

One sheet, 29 rows × 72 columns. **OPEN.**

- Columns: `SR.NO | Name | Cat | SITE |` then **31 day-groups of two columns
  each** — a `P` column (days present) and an `O` column (overtime hours) —
  then `Days | OT | OTCD | Total Days | Per Day Salary | Total Salary`.
- The day-of-month numbers sit in row 1 above each *pair*; row 2 carries the
  literal `P` / `O` sub-headers. **Another two-row banded header.**
- `OTCD` is overtime converted to days at **8 hours = 1 day** (13 OT → 1.625).
  `Total Days = Days + OTCD`; `Total Salary = Total Days × Per Day Salary`.
  **The arithmetic foots on every row checked.**
- **`Cat`** is a trade: ACCOUNT, SALES/PURCHASE, SUPERVISOR, FITTER, WELDER,
  HELPER, WEL/FIT.
- **`SITE` is a first-class column on every labour row**, and its values are
  several concurrent sites plus `OFFICE`. **Bangalore is among them** — see
  §6.2, this independently confirms DOMAIN.md §1.
- **DEFECT — `#VALUE!` in two cells** (`BO2`, `BP2`, the `Days` and `OT`
  sub-header row). The Excel error the taxonomy asks about is genuinely present
  in this batch, in exactly one document.

### 3.4 `RD_fire.xlsx` — the largest, and the only real GST block

Six sheets. The first tab holds **two documents stacked on one sheet**. **OPEN.**

**Rows 1–77 — a cost abstract / summary.**
- Document control: `Project:…`, `BOQ NO. 1`, **`REV.00`**, `DATE:` with a
  genuine datetime value.
- Sections `A` / `B` / `C` (pump; other fire work; approvals & liasoning), each a
  one-line roll-up of a numbered group.
- Amount columns are a **three-way band**: `Supply | Installation | Total`.
- **GST is applied per section AND per leg.** Section A carries four separate tax
  rows — `SGST (Supply of Pump)`, `CGST (Supply of Pump)`, `SGST (Installation)`,
  `CGST (Installation)` — each with its rate in its own cell (`0.09`) and its
  amount in the matching leg's column. Section B carries a plain `SGST`/`CGST`
  pair; section C carries `SGST on LIASONING WORK` / `CGST on LIASONING WORK`.
  Each section then has a `SUB-TOTAL … (With Tax)`.
- Two **AMC option blocks** (`Option-1: With Comprehensive AMC`, `Option-2:
  Without…`), each a six-year schedule, each footed with a **single `GST` at
  `0.18`** rather than a CGST/SGST split. **Two different tax expressions in one
  workbook.**
- **DEFECT — item numbers out of order and duplicated.** In *both* AMC blocks the
  rows read `1, 2, 3, 4, 6, 5` — the 5th and 6th year rows carry swapped
  numbers. The same six numbers then repeat in the second block. Surface, do not
  fix.

**Rows 79–731 — the BOQ proper**, with its own header at r80/r81:
- `Sr. | DESCRIPTION | Qty | Unit |` then **`Rate` as a three-column band
  (`Supply | Installation | Total`)** and **`Amount` as a three-column band
  (`Supply | Installation | Total`)**, then `Remark`.
- A **`Total` rate column** — supply rate plus installation rate on one line —
  which the system has no field for (see §6.6).
- Item numbering: sections `A`/`B`/`C`, numeric items, dotted sub-items (`1.1`),
  and specification sub-paragraphs `a.` `b.` `c.` `d.` **as separate physical
  rows carrying no item number at all**.
- 25 hidden rows on this sheet.

**Five `Qty.-*` sheets — quantity takeoffs**, not BOQs. Between 34 and 809 rows,
with 13–71 hidden rows each.

### 3.5 `Walkeshwar_Blank_BOQ_Fire_Hydrant_&_Sprinkler.xls` — a blank BOQ over eight hidden takeoffs

Eleven sheets, **eight of them hidden**. **OPEN.**

- **The seller named on the BOQ sheet is not Samruddhi.** It is a different fire
  contracting firm. Whatever this workbook is — a competitor's template, a
  format the client was handed, a peer's document — it is **not the client's own
  paperwork**, and no convention in it should be attributed to them without
  asking. **Candidate §7 gap.**
- `FF BOQ` sheet: 464 rows. Deep **four-level dotted item numbering** —
  `2.1.4` with children `2.1.4.1`, `2.1.4.2`. See §6.4.
- **The eight hidden sheets are quantity takeoffs** with floors as columns —
  `GR`, `P1`–`P6`, `service`, `1ST`–`12TH`, `TER`: **21 floor columns**, plus
  `Total`, plus an **`Extra 10%`** column (the design-safety-factor, expressed
  here as a *column* rather than a row) and an `MS Bracket` column. No rates, no
  amounts anywhere on them.
- **DEFECT — sheet names carry stray whitespace**: `'FF BOQ '`,
  `'Elec Installations '` (trailing). `RD_fire.xlsx` has the same problem
  including a **leading** space, `' FIRE BOQ'`. A lookup by trimmed name fails.

### 3.6 `Mundra_Gujrat_Fire_fighting.xlsx` — the cleanest supply/installation split

One sheet, 150 rows, "Subcon BOQ". **OPEN.**

- **Two-row banded header**: r2 declares `Supply` over columns E–F and
  `Installation` over G–H; r3 declares `Unit Rate | Amount` beneath each. Plus
  `Sr | Description | Unit | Qty`.
- **Item numbering is one flat running series with no sub-items**, and **section
  heading rows consume a number in that same series** — the heading
  "FIRE PUMP HOUSE & EQUIPMENTS" is item 1, "MAIN PUMP" is item 2, "STAND BY
  PUMP" is item 4. See §6.3.
- **The supply rate on installation-only lines is the literal string `NA`.**
  Not blank, not zero, not `-`. A non-numeric sentinel in a rate column.
- Several lines carry a quantity and an amount of `0` with no rate — nil-priced
  lines, which DOMAIN.md §2.4 already says are valid.
- Payment terms at the foot include **`10% Advance for Site Mobilization`** —
  the only mobilisation reference in the entire batch (§7.2).
- **DEFECT** — at least one description cell begins with a newline.

### 3.7 `Kalyan_Site.xlsx` — two companies in one workbook, and the `R.O.` legend

Four sheets. **OPEN.**

- **`Sheet1` is Samruddhi's own quotation cover**: `PRICE SUMMARY`, addressed
  `To,` a named individual, with sections `A`–`G` and **`Supply Amount` and
  `Installation Amount` as two separate columns per section**, a `Total` row,
  `TAXES WILL BE EXTRA`, and eight numbered terms & conditions. Section subtotals
  foot exactly on both columns.
  - **DEFECT — two different sections carry byte-identical supply *and*
    installation subtotals.** Two unrelated systems priced to the rupee the same
    on both legs is far more likely a copy-paste than a coincidence. Surface,
    do not fix.
- **`BOQ` is a *different company's* document** — a consulting engineer's, with a
  full document-control block: `Project`, `Prepared By`, `Checked By`,
  `Approved By`, `Doc. No.`, **`Revision: 1`**, `Sheet No.: 1 of 3`, `Date`.
  See §6.5.
- **The `BOQ` sheet carries a legend that decodes the batch's sentinel values**:
  - `I.R or R.O. means Item Rate Only.`
  - `` `S' under Rate and Amount shall mean … ``
  These are documented, intentional non-numeric markers — see §5.4.
- `Measurment sheet` tab is **misleadingly named**: it is a **quantity takeoff /
  design schedule** (building configuration, pump room, booster pump; items as
  rows, pipe sizes `Ø50`…`Ø250` as columns), not a measurement sheet in the RA
  sense. Do not treat the tab name as its classification.
- **DEFECT — mojibake in the size headers**: the `Ø` diameter symbol is corrupted
  in the takeoff tab's header row.
- One hidden row on the takeoff tab.

### 3.8 `Abhilasha.xlsx` and `BOQ_Kandivali.xls` — one template, two sites

Two files sharing a sheet vocabulary almost exactly: `Summary`, `PUMP ROOM`,
`HYDR.SYSTEM`, `SPRINKLER BOQ`, `ELECTRICAL PANEL`, `F.EXT.`, a fire-alarm tab
and a makes list. Treat as **one template family**. **OPEN.**

- `Summary` is a **cost abstract**: `PART | DESCRIPTION | AMOUNT`, parts `A`–`G`,
  `GRAND TOTAL`. **Seven sections, not three.** The grand total foots exactly.
- Blank filler rows are interleaved between every section row on the summary.
- Both carry **`R.O.` in the quantity column** — see §5.4.
- `Abhilasha.xlsx` `Summary` has one hidden column.
- The `make list` / `Make list` tabs are **approved-manufacturer lists** — 83
  rows, no prices. A document type the system does not model, and one that also
  appears as a per-line `Approved make` column elsewhere (§3.9).

### 3.9 The quotations

`Quotation_for_Ground+9th_Floor.xlsx`, `Skyline.xlsx`, `BOQ_New_(Recovered).xls`,
`New_Qoute.xlsx`. **OPEN.**

- **`BOQ_New_(Recovered).xls` opened cleanly. It is not damaged.** All 184 rows
  of its single sheet read without error. "(Recovered)" appears to record an
  Excel repair that succeeded, not surviving corruption.
  - Its columns are `SR | ITEMS WITH DESCRIPTION | Unit | A Wing | Comm | Qty |
    Rate | Amount`. **`A Wing` and `Comm` are area columns** and `Qty` is their
    sum — a second, independent confirmation of DOMAIN.md §2.3.
  - Its specification text is **split across seven consecutive physical rows**,
    each holding one fragment of the sentence, none carrying an item number; the
    priced size rows follow, **also carrying no item number** (the description
    *is* `150 mm dia`). One logical line spans eight rows.
  - Payment terms name **`65% As per Running Bills`** and `GST 18% Will be added
    in Bills` — GST stated as a single 18%, not split.
- **`Skyline.xlsx` carries the client's own buying cost in the same sheet as the
  quoted price.** Beyond the labelled `SITC → RATE | AMOUNT` band there is an
  **unlabelled column of consistently lower rates**, and beside it a column
  pairing a supplier name with a rate. An importer that reaches for "the rate
  column" positionally can silently import cost as price. **Candidate §7 gap.**
- **`Quotation_for_Ground+9th_Floor.xlsx` uses two different sub-item
  conventions on one sheet** — see §6.4 — and carries an **approved-make column
  per line**.
- **`New_Qoute.xlsx` is a PDF→Excel conversion and is structurally unsound.**
  Tabs are named `Table 1/2/3` and are arbitrary *fragments of one continuous
  document*, not sections; Table 2 opens mid-list. **The column layout differs
  between tabs** — Table 1 has six columns with the item number in column A;
  Tables 2 and 3 have five, shifted one left, **with the item number embedded in
  the description text** (`8      M. S Seamless Reducer…`). Header cells contain
  literal newlines (`SR\nNO.`, `UNIT\nRATE`). Summary text has spilled into the
  line-item region. Its quantity column holds **`45 Mtr.` — a number and a unit
  in one cell** — while a *separate* numeric column holds `45`.
  **Do not use this file as evidence of any convention.** It is evidence only of
  what a converted PDF looks like.

### 3.10 `fire_e_fighting-Turbhe.xlsx` — a blank BOQ with the fullest column set

**OPEN.** Columns: `S No | PARTICULARS | Unit | Qty | supply rate |
Installation rate | supply amount | Installation amount | Total Amount`.

- **Every rate is blank and every amount is 0.** This is an unpriced template
  issued for pricing, not a completed BOQ.
- Party block (`CLIENT`, `Property`, `Location`, `Agency`, `Office`, `Date:`) is
  present but **entirely empty** — it shows the *shape* of their party block with
  none of the data.
- Parent/child numbering `7` → `a`–`e` in the item column, parents carrying
  description only.
- **DEFECT** — at least one priced-shaped row carries no item number at all.

### 3.11 `Bhaveshwar_Callista_roadpali.xlsx` — a purchase-side rate list

**OPEN.** `Sr.No. | Material | Qty | Unit |` and a **rate column headed with a
supplier's name**. Two rows have a quantity but no rate — not yet quoted. This is
a buying document, not a BOQ; classify it with `purchase.py`'s world, not
`boq.py`'s.

### 3.12 `Khargar_38th_Floors.xls`

**OPEN.** Despite the filename, **this sheet has no floor columns** — six columns
only: `SR. NO. | Item Description | Unit | Qty | Rate | Total Amount`. The "38th
floor" is the building, not the schedule's shape.

- Section headers use **Roman numerals** (`I`), a fourth section convention.
- **Item numbers are stored as floats** — `1.0`, `2.0`, `13.0` — exactly the
  problem `boq.py::_item_no` exists to absorb (DOMAIN.md §2.2).
- Numbering is **not dense**: it runs 1–4 then jumps to 8.
- **DEFECT — inconsistent child labels within a single parent**: sub-items run
  `a`, `b`, `c`, `d`, `e`, `f`, then **`g)`** with a bracket.

---

## 4. Capacity — measured, not inferred (Step 5.1)

Method: every sheet of every workbook was walked cell by cell. "Priced line" =
a row carrying at least two numeric values **and** a descriptive string, after
excluding rows whose text matches header / total / subtotal / rate / amount /
safety-factor / note patterns. A representative line dict was built **in the
exact shape `boq.py` stores** (`line_id`, `item_no`, `parent_item_no`, `section`,
`is_header`, `description`, `remark`, `unit`, `area_qty`, `total_qty`, the six
supply fields, the six install fields), `json.dumps`'d, and measured.

**Bytes per line, measured:**

| Area/floor columns | 0 | 2 | 5 | 10 | 21 | 38 |
|---|---|---|---|---|---|---|
| desc 60 chars | 574 | 608 | 662 | 752 | ~950 | 1,256 |
| desc 120 chars | 634 | 668 | 722 | 812 | ~1,010 | 1,316 |
| desc 240 chars | 754 | 788 | 842 | 932 | ~1,130 | 1,436 |

Each additional area column costs **~18 bytes per line**.

**The ten largest sheets by serialised estimate**, against `MAX_JSON_BYTES =
300,000`:

| File | Sheet | Used rows | Priced lines | Kind | Est. bytes | % of cap |
|---|---|---|---|---|---|---|
| `RD_fire.xlsx` | ` FIRE BOQ` | 725 | 178 | PRICED | 99,502 | 33% |
| `Mundra_…xlsx` | `Subcon BOQ` | 150 | 100 | PRICED | 65,400 | 22% |
| `fire_e_fighting-Turbhe.xlsx` | `Table 2` | 133 | 69 | PRICED | 51,474 | 17% |
| `Kalyan_Site.xlsx` | `Measurment sheet` | 166 | 77 | **TAKEOFF** | 41,426 | 14% |
| `Walkeshwar_…xls` | `FF BOQ ` | 464 | 67 | PRICED | 39,597 | 13% |
| `Walkeshwar_…xls` | `INTERNAL SPRI QTY TYPICAL FLOOR` | 71 | 61 | **TAKEOFF** | 33,672 | 11% |
| `RD_fire.xlsx` | `Qty.-SPRINKLER ` | 809 | 59 | **TAKEOFF** | 31,565 | 11% |
| `Walkeshwar_…xls` | `INTERNAL SPRI QTY NTA AREA` | 67 | 57 | **TAKEOFF** | 31,464 | 10% |
| `Kalyan_Site.xlsx` | `BOQ` | 138 | 52 | PRICED | 30,056 | 10% |
| `Khargar_38th_Floors.xls` | `BOQ` | 122 | 43 | PRICED | 29,885 | 10% |

### 4.1 Verdict: **no sheet in this batch breaches `MAX_JSON_BYTES`. Nothing is BLOCKING.**

The largest priced schedule in the batch serialises to **~99.5 KB, one third of
the 300,000-byte cap**. At **178 priced lines** it sits at roughly **42% of the
~428-line ceiling** the code's own comments cite.

### 4.2 Why used-row count is a bad proxy, in both directions

- `RD_fire.xlsx` `Qty.-HYDRANT ` has **512 used rows and 6 priced lines**.
- `Walkeshwar` `FF BOQ ` has **464 used rows and 67 priced lines** — 14%.
- `RD_fire.xlsx` ` FIRE BOQ` has 725 used rows and 178 priced lines — because a
  single item's specification occupies four to eight consecutive rows.

**Row count over-states line count by 3–85× in this batch.** File size on disk is
worse still: the largest file (451 KB) and the second largest (333 KB) are large
because of styling and hidden takeoff sheets, not because of line count.

### 4.3 The floor-column multiplier

**The widest area/floor structure found is 21 columns** — `GR`, `P1`–`P6`,
`service`, `1ST`–`12TH`, `TER` — on `Walkeshwar`'s hidden takeoff sheets and
mirrored in the RD_fire `Qty.-*` tabs.

**Those are takeoffs, not BOQs, and their rows must not be counted against any
ceiling.** They carry no rate and no amount anywhere.

But the multiplier is the thing to watch, and it is worth stating plainly:

- At **21 area columns**, a line costs ~950–1,010 bytes, so the cap is reached at
  roughly **300–315 lines** rather than ~428.
- At **38**, ~1,256–1,316 bytes, so the cap is reached at roughly **225–240
  lines**.

**Nothing in this batch combines a wide floor structure with a long priced
schedule.** The two risks exist in separate documents: the long schedules
(RD_fire, Mundra, Walkeshwar FF BOQ) are all narrow, and the wide sheets
(21 floor columns) are all short takeoffs. **A future project that is both would
breach the cap at a line count well under 428**, and that combination is
plausible — `Walkeshwar` is a real building with 21 levels and a 464-row BOQ,
they simply live on different tabs today. **Candidate §7 gap.**

### 4.4 Priced schedule vs quantity takeoff — how to tell them apart

The distinction is load-bearing and the filenames and tab names **will mislead
you**. Signature of a takeoff, all four present:

1. Locations or floors as **columns** (`GR`, `P1`, `1ST`…`TER`), items as rows.
2. A `Total` column, and a **design-safety-factor column or row** — in this batch
   spelled **`Extra 10%`**.
3. **No rate column and no amount column anywhere on the sheet.**
4. Frequently **hidden** (8 of 11 sheets in `Walkeshwar`) — it is working
   material the author did not intend a reader to open.

Two tab names in this batch are actively wrong: `Kalyan_Site.xlsx` →
`Measurment sheet` is a **takeoff**, and `Measurement_Sheet_updated.xlsx` →
`Sheet1` is a **joint measurement pro-forma**, not a takeoff, despite having
sizes as columns — it is distinguished by the two-party signature block.

---

## 5. Data defects found (Step 4)

Per DOMAIN.md §6, these are recorded to be **surfaced, not repaired**. None was
altered.

| Defect | Where | Notes |
|---|---|---|
| `#VALUE!` errors | `ATTENDANCE_SHEET.xlsx` (2 cells) | The only Excel error values in the batch |
| **Non-numeric value in a QUANTITY column** | `Walkeshwar` `FF BOQ `, `BOQ_Kandivali` + `Abhilasha` `SPRINKLER BOQ` | **`R.O.` — see §5.4 below** |
| **Non-numeric value in a RATE column** | `Mundra` `Subcon BOQ` | literal string **`NA`** on supply-only-absent lines |
| Number and unit in one qty cell | `New_Qoute.xlsx` | `45 Mtr.` as text |
| Item numbers stored as floats | `Khargar_38th_Floors.xls` | `1.0`, `13.0` — the `_item_no` case |
| Duplicate item numbers | `RD_fire.xlsx` (AMC blocks) | Confirms DOMAIN.md §2.2 independently |
| Item numbers out of sequence | `RD_fire.xlsx` | `1,2,3,4,6,5` in both AMC blocks |
| Non-dense numbering | `Khargar` (4→8), `Quotation_for_Ground+9th` (skips `4`; children `a,b,d` — no `c`) | Gaps are normal, not corruption |
| Inconsistent child labels in one parent | `Khargar_38th_Floors.xls` | `a`–`f` then `g)` |
| Totals row misaligned with header | `Measurement_Sheet_updated.xlsx` Sheet1 | Stray total in an unheaded column; two headed columns untotalled |
| Unit contradicts the row | `Measurement_Sheet_updated.xlsx` Sheet3 | Length expression tagged `Nos` |
| Identical subtotals on two sections | `Kalyan_Site.xlsx` Sheet1 | Both legs identical to the rupee — likely copy-paste |
| Mojibake | `DC-SF.xlsx` (en-dash), `Kalyan_Site.xlsx` (`Ø`) | Encoding round-trip damage |
| Leading/trailing whitespace in sheet names | `RD_fire.xlsx` (` FIRE BOQ`), `Walkeshwar` (`FF BOQ `) | Lookup by trimmed name **fails** |
| Leading newline inside description cells | `Mundra`, `New_Qoute` | |
| Hidden rows | `RD_fire` (25+13+42+71), `Kalyan_Site` (1) | |
| Hidden columns | `Abhilasha.xlsx` `Summary` (1) | |
| Hidden sheets | `Walkeshwar` — **8 of 11** | All takeoffs |
| Merged cells | Pervasive — 225 ranges on one `Kalyan_Site` tab alone | |

**No raw Excel date serials were found in this batch.** Dates appear either as
genuine datetimes (`RD_fire`) or as free text (`Date : 15/07/2026`,
`DATE: 10.04.2025`, `01 07 2024` — three different formats). DOMAIN.md §6 lists
date serials as an observed defect; that observation came from elsewhere and is
**not contradicted**, merely not reproduced here.

### 5.4 `R.O.` — the sentinel the over-claim guard would swallow

This is the finding §5.1 was told to hunt for, and it is real.

**`R.O.` appears as a literal string in the QUANTITY column**, on priced-shaped
rows:

- `Walkeshwar` `FF BOQ `, on rows whose neighbours are item no / description /
  unit `Each` — the quantity cell reads `R.O.` and the amount cells read `0.0`.
- `BOQ_Kandivali.xls` and `Abhilasha.xlsx`, `SPRINKLER BOQ` tabs, same shape.

**And the batch documents its own meaning.** `Kalyan_Site.xlsx` `BOQ`, in its
notes block: **"I.R or R.O. means Item Rate Only."** A second legend line in the
same block assigns a meaning to a bare **`S`** appearing "under Rate and Amount".

So these are **deliberate, documented sentinels**, not typos: the line exists and
is rate-only — quantity to be measured later. They are not zero and they are not
missing.

**Consequences, all OPEN:**

1. The over-claim guard sums the approved-quantity column. A string there either
   raises or silently coerces to `0.0`. Coercing to zero means **the approved
   quantity for that line becomes zero, and every claim against it over-claims**
   — a hard block on a legitimate line. That is the inverse of the error the
   system exists to catch, exactly as DOMAIN.md §6 warns about collapsing
   "uncertified" into "zero".
2. `boq.py::_num` falls back to a default rather than raising — so an `R.O.`
   quantity would arrive as `0.0` **silently**, with nothing surfaced.
3. Per DOMAIN.md §6 the correct handling is to **surface and name it**, not to
   coerce it and not to drop the line.

**Candidate §7 gap.** Recorded here for Manas to rule on; not added to ABOUT.md
§7 by this pass.

---

## 6. Cross-check against DOMAIN.md (Step 5.2)

DOMAIN.md was reverse-engineered from **one** BOQ and **one** RA bill. This batch
is 16 more files from other projects and other authors. **DOMAIN.md is not edited
by this pass.** Every row below is **OPEN**.

| # | DOMAIN.md claim | Verdict | Evidence |
|---|---|---|---|
| §1 | Several concurrent sites; site is a first-class field, not a label | **CONFIRMED** | `ATTENDANCE_SHEET.xlsx` has a `SITE` column on every labour row with four distinct values including `OFFICE` |
| §1 | Bangalore is an observed site | **CONFIRMED** | `ATTENDANCE_SHEET.xlsx`, `SITE` column |
| §2.1 | A BOQ is grouped into sections with subtotals | **CONFIRMED** | `Abhilasha`, `Kalyan_Site` Sheet1, `RD_fire`, `BOQ_New_(Recovered)`, `Khargar` |
| §2.1 | "The client's seeded schedule has three" | **EXTENDED** | Section counts run to **seven** (`Abhilasha`, `Kalyan_Site`). Three is not a ceiling |
| §2.1 | Section codes are A/B/C | **EXTENDED** | Also Roman `I` (`Khargar`), `PART A`–`G` (`Abhilasha`), and numeric sections sharing the item series (`Mundra`) |
| §2.2 | Parent carries the spec, no qty and no rate | **CONFIRMED** | `Skyline`, `Quotation_for_Ground+9th`, `Khargar`, `fire_e_fighting-Turbhe`, `RD_fire` |
| §2.2 | Children are the same spec at different sizes | **CONFIRMED** | Universal — children are `150 mm dia`, `100 NB`, `80 NB` throughout |
| §2.2 | `item_no` is not unique; repeats within a document | **CONFIRMED** | `RD_fire` repeats `1,2,3,4,6,5` across two AMC blocks on one sheet |
| §2.2 | Item numbers get stored as floats | **CONFIRMED** | `Khargar_38th_Floors.xls` |
| §2.2 | The hierarchy is two levels (`24` / `24.a`) | **EXTENDED** | `Walkeshwar` runs **four levels**: `2.1.4` → `2.1.4.1`. See §6.4 |
| §2.3 | Area/floor columns exist and a line's qty is broken down by them | **CONFIRMED** | `BOQ_New_(Recovered).xls` — `A Wing` and `Comm`, summing to `Qty` |
| §2.3 | Which columns exist is declared per section, not per document | **NOT TESTED** | No document in the batch declares *different* area sets on different sections. Not contradicted; simply not exercised |
| §2.4 | Every line priced twice, supply and installation, on independent tracks | **CONFIRMED** | `Mundra`, `fire_e_fighting-Turbhe`, `RD_fire`, `Kalyan_Site` Sheet1 — four independent documents |
| §2.4 | A line may carry one track only | **CONFIRMED** | `Mundra` — supply rate is literally `NA` on installation-only lines |
| §2.4 | Nil-priced lines are valid | **CONFIRMED** | `Mundra` — real qty, no rate, amount `0` |
| §2.5 | Rate = base rate + escalation % | **NOT FOUND** | **No document in this batch carries a base-rate or escalation column.** Every rate is a single agreed figure. Not contradicted, but unsupported by 16 further files |
| §2.6 | A revision is a new record, and revisions are real | **CONFIRMED / EXTENDED** | Revision is an explicit **field on the client's own documents** — `REV.00` (`RD_fire`), `Revision: 1` (`Kalyan_Site`) — alongside a `Doc. No.` See §6.5 |
| §3.7 | Retention exists as a concept but the client's bills show none | **STRONGLY CONFIRMED** | **Zero retention hits across all 18 documents.** See §7.1 |
| §3.7 | Mobilisation advance and its recovery | **PARTIALLY EXTENDED** | One document names a mobilisation advance as a *term*; no document shows a *recovery*. See §7.2 |
| §4.1 | RA bill is headed TAX INVOICE, two number series | **NOT TESTED** | **There is no RA bill and no tax invoice in this batch.** See §7.5 |
| §4.3 | CGST+SGST vs IGST is a stored determination | **CONFIRMED, and no counter-example found** | Four CGST rows, four SGST rows, **zero IGST**. See §7.3 |
| §4.3 | Tax at 9% + 9% | **CONFIRMED** | `RD_fire` stores `0.09` per tax row |
| §4.4 | HSN/SAC is a per-line field | **CONFIRMED (on the challan) / CONTRADICTED (on the BOQ)** | `DC-SF.xlsx` carries `HSN / SAC Code` per line. **No BOQ or quotation in the batch carries HSN at all** — `RD_fire` taxes at *section* level with no per-line code |
| §4.5 | Rounding-off is an explicit line | **NOT FOUND** | **Zero genuine rounding-off rows in 18 documents.** See §7.6 |
| §5.1 | Delivery challan: quantity and unit only, no rates | **CONFIRMED** | `DC-SF.xlsx` exactly |
| §5.1 | The consignee is Samruddhi's own site | **CONTRADICTED** | See §6.1 — this is the batch's one direct contradiction |
| §5.2 | Their POs carry no GST / one running series / a `Pcs` column | **NOT TESTED** | No purchase order in the batch |
| §6 | Their data is imperfect and must survive | **CONFIRMED, emphatically** | 18 distinct defect classes — §5 |
| §6 | Raw Excel date serials | **NOT REPRODUCED** | No serials here; three *other* date formats instead |

### 6.1 The one direct contradiction — the challan's consignee

DOMAIN.md §5.1 states, as a reason rather than an observation:

> "The consignee is **Samruddhi's own site**, because they are moving their own
> material to their own store on a project, not selling it to anyone."

`DC-SF.xlsx` does not do that. It carries a **`Consignee Name` that is a third
party** — an unrelated private limited company — and a separate **`Consignee
Address` that is a *different* company's premises** at the Mohali site.

So on the one real challan in the batch, **the consignee is neither Samruddhi nor
Samruddhi's own store**, and consignee-name and consignee-address are two
independent fields that need not describe the same entity.

The *structural* half of §5.1 (quantity and unit only, no rates) is confirmed.
The *reason* given for the consignee is contradicted by the only specimen.

**This matters because it is a reason, and reasons in DOMAIN.md are load-bearing
— they are what stops a later agent "simplifying" a field away.** A model built
on "consignee is always us" would have no place to put either value here.

**OPEN. DOMAIN.md not edited. Manas rules.**

### 6.2 Site as a first-class field — now independently evidenced

DOMAIN.md §1 infers this partly from the POs. `ATTENDANCE_SHEET.xlsx` evidences
it directly and from a different direction: **labour is allocated per site, daily,
and costed per site.** Site is a dimension of their cost data, not a caption.

### 6.3 Section headings that consume an item number — EXTENDS §2.2

DOMAIN.md's model is: sections are structural, and *within* a section items are
numbered, with spec parents carrying children. `Mundra` breaks that cleanly —
its section headings **are items** in the running series. An importer that
assumes "a numbered row is a priced row" mis-reads this document, and one that
assumes "a section header is unnumbered" mis-reads it the other way.

`is_header` already exists on the stored line shape, so the record can express
this. The observation is that **the number and the header-ness are independent**,
which the current model does not say out loud.

### 6.4 Sub-item numbering has at least five conventions — EXTENDS §2.2

Across the batch, "the children of item N" are written as:

1. `a`, `b`, `c` in the **item-number column** — `Khargar`, `Skyline`,
   `fire_e_fighting-Turbhe`
2. `a)`, `b)` **inline in the description column**, item column blank —
   `Quotation_for_Ground+9th_Floor` (**which also uses convention 1, on the same
   sheet, for a different parent**)
3. **Nothing at all** — children identified only by position under the parent,
   description reading `150 mm dia` — `BOQ_New_(Recovered)`
4. **Dotted decimals to four levels** — `2.1.4.1` — `Walkeshwar`
5. `a.`, `b.`, `c.` as **specification sub-paragraphs on their own rows**, which
   are *not* children at all but continuation prose — `RD_fire`

Convention 5 is the dangerous one: it looks exactly like convention 1 to a
parser, and it is not a line. Convention 2 co-existing with convention 1 in one
file means **the convention cannot be detected per-document and applied
per-document.**

### 6.5 Revision and document control are fields on their documents — EXTENDS §2.6

DOMAIN.md §2.6 argues revisions from first principles (a claim's basis must not
move). The batch shows the client's world already labels them: `BOQ NO. 1` /
`REV.00`, and `Doc. No.` / `Revision: 1` / `Sheet No.: 1 of 3` /
`Prepared By` / `Checked By` / `Approved By`.

Two things follow, both OPEN:

- Revisions are **numbered from zero** in at least one house style (`REV.00`).
- The *consultant's* document number and revision are **the customer's
  identifiers**, not ours. A revision chain keyed only to our own record has
  nowhere to record "this is their Doc. No. `nnnn-nn-nn` Rev 1" — which is
  what the main contractor will quote back.

### 6.6 A `Total` rate column — EXTENDS §2.4

`RD_fire` bands both `Rate` and `Amount` into three columns each: `Supply`,
`Installation`, **`Total`**. The stored line shape has `supply_rate`,
`install_rate`, `supply_amount`, `install_amount` — and no combined field.

That is almost certainly *correct* (a derived total should not be stored twice),
but it is worth recording that **their documents print a combined rate**, so the
renderer needs it even though the record should not hold it.

---

## 7. Open questions these documents were meant to answer (Step 5.3)

### 7.1 Retention — **ANSWERED (negative), and strongly**

**No document in this batch deducts retention.** A case-insensitive regex for
`retention` / `retension` / `withheld` / `hold back` across every cell of all 16
workbooks returns **zero matches**.

This does not merely fail to find retention — with 16 further documents from
multiple projects and multiple authors, it is meaningful corroboration of
DOMAIN.md §3.7's decision to **keep the deductions list in the shape and keep it
empty**. Do not populate it. **OPEN, but the evidence points one way.**

*Caveat, honestly stated:* retention is deducted on a **bill**, and there is no
bill in this batch (§7.5). Absence of retention in BOQs and quotations is weaker
evidence than absence in nine RA bills would be.

### 7.2 Mobilisation advance and its recovery — **PARTIALLY ANSWERED**

**Present as a term, in exactly one document.** `Mundra_Gujrat_Fire_fighting.xlsx`
carries, in its payment-terms block: **`10% Advance for Site Mobilization.`**

That is the first evidence in the project that a mobilisation advance is real for
this client and not just standard-practice background.

**Its recovery is not shown anywhere.** No document expresses an instalment,
a running advance balance, or a deduction against an advance. So the half of
DOMAIN.md §3.7 that matters for the record shape — *how* recovery is expressed —
is still unanswered.

Related but distinct: **advance payment terms are near-universal** in the batch
(25%/50%/30%/20% against work order, supply, delivery, running bills,
completion). Those are commercial payment terms on a quotation, **not**
mobilisation advances, and should not be conflated. One document also promises
`75% Against Performa Invoice`, which is a proforma trigger, not an advance
recovery.

### 7.3 Place of supply / IGST — **ANSWERED (negative). This is the headline.**

**Not one document in this batch charges IGST.** A word-boundary regex for
`igst` across every cell of all 16 workbooks returns **zero matches**.

What GST *is* charged:

- `RD_fire.xlsx` is **the only document with a real tax block**: four `CGST` rows
  and four `SGST` rows, each at `0.09`, applied **per section and per leg**
  (supply taxed separately from installation), plus two AMC blocks taxed at a
  single `0.18`.
- Everything else defers tax entirely: `GST Extra as Applicable`, `TAXES WILL BE
  EXTRA`, `GST extra as applicable on item to item`, `GST 18% Will be added in
  Bills`.
- `place of supply` appears **nowhere**.
- Exactly **one GSTIN** appears in the whole batch — the seller's own, on the
  delivery challan, state code **27 (Maharashtra)**. **No customer GSTIN
  appears anywhere.**

**On the out-of-state question specifically:** the batch *does* contain
out-of-state work — a Gujarat site (`Mundra`), a Punjab delivery destination
(`DC-SF`, Mohali), and Bangalore labour (`ATTENDANCE_SHEET`). **None of them
carries a tax determination of any kind.** The Gujarat BOQ has no tax block; the
Punjab document is a challan, which by its nature carries no tax.

So the most valuable question in the batch is answered like this:

> **This batch provides no example of IGST, and therefore no counter-example to
> the CGST+SGST treatment already observed. It also provides no out-of-state
> document that charges tax at all — so it does not resolve the question, it
> just fails to disturb it.**

DOMAIN.md §4.3's stance — **a stored per-bill determination with a default, not a
hardcoded comparison** — survives this batch unchallenged and is, if anything,
better supported: the client's own documents overwhelmingly **defer the tax head
to billing time** ("GST extra as applicable"), which is exactly a decision made
per bill rather than derived from the BOQ.

**Per DOMAIN.md §4.3 this pass does not conclude what the law requires. It still
goes to their CA.** **OPEN.**

### 7.4 Turnover / e-invoicing threshold — **NOT ANSWERED**

**Zero hits** for `turnover` or `aggregate turnover`. No document states a
turnover figure, and none of the summaries aggregates beyond a single project's
cost. Nothing here bears on the e-invoicing threshold. (DOMAIN.md §4.8 puts
e-invoicing out of scope regardless.)

### 7.5 Separate Tax Invoice No and RA Bill No series — **NOT ANSWERED, because there are no bills**

**Zero hits** for `tax invoice`, and zero for `RA bill` / `running account`.

**This batch contains no RA bill, no tax invoice, no proforma and no purchase
order.** The number-series question — is the two-series pattern universal or was
it one document's habit — cannot be advanced by this batch at all.

The only document-number series observable here:

- **Challan number** — a bare running integer, no prefix, no financial year.
- **BOQ / document number** — the *consultant's*, formatted `nnnn-nn-nn` with a
  separate `Revision`, and `BOQ NO. 1` with `REV.00` elsewhere.

Neither is a bill series. **OPEN.**

### 7.6 Rounding-off line — **NOT FOUND**

Zero genuine rounding-off rows. *(A naive substring search returns 76 hits; every
one is the word `Ground`, `underground` or `Background`. This is recorded because
the next person to grep for it will get the same 76 hits and should not believe
them.)*

Consistent with §7.5: rounding-off is a feature of the **tax invoice**, and there
is no tax invoice here.

---

## 8. New document types (Step 5.4)

### 8.1 MEASUREMENT SHEET — **FOUND. Three specimens.** ★ highest value

The BoQ → Measurement → RA-Installation bridge that Phase 3 needs and had no
sample of. `Measurement_Sheet_updated.xlsx` provides **both** a blank pro-forma
and two filled examples. Full structure in §3.1. The design-critical facts:

1. **No item numbers.** Nothing joins a measurement row to a BOQ `line_id` or
   even to an `item_no`. The only join is *(description + diameter + unit)*, a
   fuzzy natural key — and DOMAIN.md §2.2 exists precisely because natural keys
   re-attribute claims. **This is the hard design problem in Phase 3 and the
   client's own paperwork does not solve it for us.** **Candidate §7 gap.**
2. **Quantity is a text arithmetic expression**, in two inconsistent notations
   (`+` and a capital `X`), with the evaluated result in a separate `Total`
   column. The expression is the *evidence* — it records each measured run — so
   it is data to preserve, not to normalise away.
3. **The JOINT variant is counter-signed by both parties.** A measurement is
   agreed, not asserted. Nothing in the system models a counter-signature, and a
   measurement's status (drafted / signed / disputed) has no field.
4. Sizes-as-columns on the blank; location-rows on the filled ones — **the same
   business document in two incompatible layouts.**

### 8.2 MERGED RA (supply + installation stacked on one sheet) — **NOT FOUND**

No RA bill of any kind is in the batch (§7.5), so the merged-RA question is
untouched. **This remains unsampled and is still about to be quoted in Phase 3.**

What the batch *does* show is that **supply and installation stacked side by side
on one sheet is the client's normal BOQ layout** — `Mundra`, `fire_e_fighting-Turbhe`,
`RD_fire` and `Kalyan_Site` all band the two legs across one row. That is
suggestive of what a merged RA would look like, but it is a BOQ layout, not a
bill, and **must not be treated as a specimen of one.**

### 8.3 Other types the system does not build today

| Type | Specimen | Note |
|---|---|---|
| **Attendance / labour costing** | `ATTENDANCE_SHEET.xlsx` | Per-site, per-day, per-trade, with OT conversion and a computed salary. Feeds installation cost. Nothing in the system touches labour |
| **Approved makes list** | `Abhilasha`, `BOQ_Kandivali`, `Kalyan_Site` (116 rows) | Also appears as a **per-line `Approved make` column** on `Quotation_for_Ground+9th_Floor` and `Skyline`. Two representations of one concept |
| **Cost abstract / price summary** | `Abhilasha`, `Kalyan_Site` Sheet1, `Skyline`, `RD_fire`, `Walkeshwar` | A one-page section roll-up that precedes the BOQ. `Kalyan_Site`'s splits supply and installation per section. Every multi-sheet workbook in the batch has one |
| **Quantity takeoff** | 15 sheets | Working material. Explicitly **not** a BOQ (§4.4) |
| **AMC schedule** | `RD_fire` | Two priced options, six-year, taxed at a flat 18%. A recurring-service annexure to a BOQ |

---

## 9. Section 8 status (Step 5.5)

The client was asked for **5 complete BOQs** and **5 as-submitted RA bills**.

### BOQs: **6 priced, but 0 verified complete. 2 are blank templates.**

| File | Priced? | Complete? |
|---|---|---|
| `RD_fire.xlsx` | Yes — but the abstract's roll-up rows are `0` except liasoning | **Partial** — the BOQ region is priced, the summary is not fully carried up |
| `Khargar_38th_Floors.xls` | Yes | **Probably complete** — single section, priced throughout |
| `Mundra_Gujrat_Fire_fighting.xlsx` | Yes | **Partial** — supply column is `NA` throughout; only the installation leg is priced |
| `Abhilasha.xlsx` | Yes | **Probably complete** — 7 sections, grand total foots |
| `BOQ_Kandivali.xls` | Yes | **Probably complete** — same template as Abhilasha |
| `Kalyan_Site.xlsx` | Yes (cover priced) | **Partial** — the cover is priced; the consultant's BOQ tab is the schedule |
| `fire_e_fighting-Turbhe.xlsx` | **No** | **Blank template** — every rate empty, every amount `0` |
| `Walkeshwar_…xls` | **No** | **Blank** — the filename says so |

**Verdict: the batch is close to the "5 complete BOQs" ask on count, but not one
of them is a *complete, all-sections, fully-priced* schedule with both legs
populated.** The nearest are `Abhilasha` / `BOQ_Kandivali` (same template) and
`Khargar`. `Mundra` is the best *structural* specimen — cleanest supply/install
banding — but is priced on one leg only.

### RA bills: **0 of 5.**

**The batch contains no RA bill at all** — not supply, not installation, not
merged, not certified, not as-submitted. Nor any tax invoice, proforma or
purchase order.

**This is the batch's principal shortfall and should go back to the client.** The
open questions that only a bill can answer — retention in practice (§7.1),
advance recovery (§7.2), the two number series (§7.5), the rounding-off line
(§7.6), cumulative/previous-balance columns, certification columns, and the
merged-RA layout (§8.2) — all remain open **because the document type that
answers them is the one type not supplied.**

---

## 10. Candidate §7 gaps — for Manas to rule on

Recorded here per the standing rules. **Not added to ABOUT.md §7 by this pass.**

1. **`R.O.` / `NA` / `S` sentinels in quantity and rate columns.** Documented,
   deliberate, and currently coerced to `0.0` silently by `_num`. A zero approved
   quantity turns a legitimate claim into a hard-blocked over-claim. §5.4.
2. **Measurement sheets carry no item number**, so there is no key to join a
   measurement to a BOQ `line_id`. Phase 3 depends on this join. §8.1.
3. **The delivery challan's consignee is a third party**, contradicting
   DOMAIN.md §5.1's stated reason, and consignee-name and consignee-address are
   independent fields. §6.1.
4. **A wide-floor × long-schedule BOQ would breach `MAX_JSON_BYTES` at ~300
   lines, not ~428.** The two ingredients exist in the batch on separate tabs of
   the same building. §4.3.
5. **Sub-item numbering has five mutually incompatible conventions, two of which
   co-exist in one file**, so the convention cannot be detected per-document.
   §6.4.
6. **A quotation workbook carries the client's own buying cost in an unlabelled
   column beside the selling price** (`Skyline`). Positional column reading can
   import cost as price. §3.9.
7. **`Walkeshwar` is another firm's document, not the client's.** Conventions
   observed in it should not be attributed to Samruddhi. §3.5.
8. **Sheet names carry leading/trailing whitespace** in two workbooks; trimmed
   lookup fails. §3.5.
9. **The consultant's `Doc. No.` and `Revision` are the customer's identifiers**
   and have nowhere to live on our record. §6.5.
10. **No `.venv/` exists in this repo** — the project runs on a global
    interpreter, and `openpyxl` is **absent** from it. This is almost certainly
    the cause of the environment-dependent skip count. §11.3.

---

## 11. Judgement calls made in this pass

Declared per the standing rules. I made these without asking.

1. **Branch (b) — moved the documents.** All 18 were loose in the repo **root**,
   so per Step 1(b) I created `client_docs/` and moved them there with `mv`. No
   file was renamed, modified or opened before the move. This is the only write
   this pass made outside `.gitignore` and `SOURCE_DOCUMENTS.md`.

2. **Used the Bash tool (Git Bash) rather than PowerShell** for file and git
   operations. The standing rules describe a PowerShell 5.1 box; Git Bash is
   genuinely present and gives `sha256sum`, `stat` and `find` directly. No
   PowerShell-specific rule was violated (no `&&` in a PowerShell call, no
   `git add .`, no `git add -A`). Flagging it because it departs from the stated
   environment.

3. **Installed `pdfplumber` into the throwaway venv**, which Step 3 did not
   name. Step 3's rung 1 (read PDFs natively) **failed** — the environment
   reports `pdftoppm` / poppler is not installed, so PDF page rendering is
   unavailable. Rather than declare the PDFs unreadable I extracted their text
   in the `%TEMP%` venv. **The project interpreter was not touched.**

4. **Did not use LibreOffice (rung 3).** It was never needed — every `.xls`
   opened with `xlrd` on the first attempt, including the "(Recovered)" file.

5. **Defined "priced line item" heuristically** for §4: a row with ≥2 numeric
   values **and** a descriptive string, excluding rows matching header / total /
   subtotal / rate / amount / note / safety-factor patterns. Any such rule is a
   judgement. It will over-count where a takeoff row has two numbers and a
   description, and under-count where a priced line's description sits in a
   merged cell on a neighbouring row. **The counts in §4 are estimates good to
   roughly ±15%, and the cap verdict has 3× headroom, so the imprecision does not
   change the conclusion.**

6. **Classified takeoff vs priced schedule by reading the header rows myself**
   rather than trusting my automated detector, which under-detected (it flagged
   1 of the 15 takeoffs). The §4.4 signature is my rule, derived from the
   documents, not something the client stated. `Kalyan_Site`'s "Measurment sheet"
   and the `Qty.-*` tabs are classified against their own tab names on that
   basis.

7. **Treated the two PDFs as duplicates of `Measurement_Sheet_updated.xlsx`
   Sheet2/Sheet3** on the strength of matching dates, matching row sequences and
   matching values. I did not do a byte- or cell-level equality proof. They are
   still inventoried separately with their own hashes.

8. **Did not report the exact `R.O.` / `NA` cell values as data** beyond naming
   the sentinel strings themselves, and suppressed all rates, party names,
   GSTINs and totals throughout, per the redaction rule — including in places
   where quoting the figure would have made a finding more vivid (e.g. §3.7's
   identical subtotals).

9. **`.gitignore` entry is `client_docs/`**, following the `backups/` precedent
   (trailing slash, preceded by a comment explaining why). I added a comment
   block in the file's existing style rather than a bare line.

10. **Marked DOMAIN.md §2.3's per-section area declaration as NOT TESTED rather
    than CONFIRMED.** `BOQ_New_(Recovered)` confirms area columns exist, but no
    document in the batch declares *different* area sets on *different* sections,
    which is the actual claim. Confirming the weaker statement would have
    overstated the evidence.

11. **Did not treat "no IGST found" as "IGST does not apply."** §7.3 reports the
    absence and explicitly declines to draw the legal conclusion, per DOMAIN.md
    §4.3.

---

## 12. What could not be determined

- **Everything that requires an RA bill.** Retention in practice, advance
  recovery mechanics, the tax-invoice / RA-bill dual series, the rounding-off
  line, previous-balance and cumulative-claim columns, certification columns,
  and the merged-RA layout. §7.5, §8.2.
- **Whether an out-of-state site attracts IGST.** No out-of-state document in the
  batch charges tax at all. §7.3.
- **Any turnover figure.** §7.4.
- **Whether area columns are declared per section.** Not exercised. §6.
- **Whether base-rate + escalation is normal.** No document in the batch carries
  either column. DOMAIN.md §2.5's claim is neither confirmed nor contradicted by
  16 further files, which is itself worth noticing.
- **The `S` sentinel's meaning.** `Kalyan_Site`'s legend line defining it is
  truncated in the cell; I did not find an instance of `S` used in a rate or
  amount column to infer it from.
- **PDF page images.** poppler is unavailable, so the PDFs were read as text
  only. Any purely visual content — a logo, a stamp, a handwritten
  counter-signature — was **not** seen. Given both PDFs match Excel tabs exactly
  in text, I judge the risk of missed content low but non-zero.
- **Whether `Walkeshwar` and `New_Qoute` reflect the client's conventions at
  all.** One is another firm's document; the other is a mangled PDF conversion.

---

*End of findings. All findings OPEN. No source file, no `.py`, no other `.md`,
and no database was modified by this pass.*
