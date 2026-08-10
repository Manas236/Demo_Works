# ABOUT — Samruddhi Fire QMS

> **Read this file at the start of every conversation before touching code.**
> It is the project's context anchor: what this app is, how each page works,
> where the landmines are, and what is deliberately unfinished.
> If you change architecture, a data shape, or a route — update this file in the
> same commit.
tax on different parts is different
1 Description
---

## 1. What this is

A **Flask quotation & catalogue system for Samruddhi Fire**, a fire-protection
contractor in India. It is a **seller-side** app: we build the catalogue, we
price it, we issue the quotation, we raise the proforma invoice against it, we
issue the tax invoice when the goods go out, and we record the customer's
incoming Purchase Order. We never issue POs here.

The document chain is **quotation → proforma invoice → tax invoice**. Each link
is derived from the one before it, never entered from scratch, and each freezes
a copy of the line items at the moment it is issued.

Each of the three is a **different commercial instrument**, which is why each is
its own module and its own record rather than a render mode of the last:

| | What it is | Creates |
|---|---|---|
| Quotation | an offer to sell | nothing binding |
| Proforma invoice | a request for money | no GST liability, no ITC |
| **Tax invoice** | **a statutory record of a supply** | **GST liability; the customer's input tax credit** |

That last row is why the tax invoice is the only one bound by **Rule 46 of the
CGST Rules, 2017** — HSN on every line, place of supply with its State code, a
reverse-charge declaration, and a serial number unique within the financial
year. The PI's own document still says "This is not a Tax Invoice" on its face,
and now names the document that is.

### There are two pipelines, not one chain

Everything above is the **sell side**. `purchase.py` is the **buy side**, and it
is deliberately a separate pipeline:

```
SELL SIDE          quotation ──► proforma invoice ──► tax invoice      money IN
                       ▲
                       │ optional, soft
                       ▼
BUY SIDE           purchase order ──► [vendor lifecycle]               money OUT
```

**A purchase order never links to a proforma or a tax invoice, and never
should.** A PI *requests* money from a customer and a TI *records a sale*;
neither has anything to say about what we paid a vendor. The GST on a PO is
**input** tax we pay, the opposite side of the ledger from a tax invoice.
Wiring the two together would be a category error.

The one link that does exist is `purchase.quotation_id` — a **soft, optional**
reference meaning "this PO is procuring for QT-0012". It is not a parent the
way a quotation parents a PI: a PO can stand entirely alone, because stock and
consumables get bought with no deal behind them. That single optional field is
what buys **job costing** (§5). The two pipelines meet at the *job*, never at
the document.

Run it:

```bash
python app.py          # http://127.0.0.1:5000
```

Dependencies — `flask`, `pymysql`, `python-dotenv`, `markupsafe`:

```bash
pip install -r requirements.txt
cp .env.example .env   # DB credentials; gitignored
```

`assets/build_assets.py` additionally needs `numpy`, `Pillow`, `scipy`. It is a
one-off artwork build script, not a runtime dependency — its output is committed
under `assets/`, so it is left commented out in `requirements.txt`.

### The one architectural rule that explains everything

**There is no `/templates` folder and no `/static` folder.** Every page is an
f-string of HTML inside a Python module, handed to `render_template_string()`.
CSS lives in Python string constants. Logos are base64 data URIs baked into the
HTML. This is deliberate: a quotation must render correctly when printed or
emailed with no server to fetch assets from.

Consequences you must respect when editing:

- HTML lives in **f-strings**, so every literal `{` and `}` in CSS/JS inside
  those strings must be **doubled** (`{{` / `}}`). Getting this wrong is the
  #1 source of breakage in this repo.
- Where a view still calls `render_template_string`, Jinja runs over the
  finished result, so `{{ }}` that survives into the output is **executed** —
  including braces that came from user input (§7.9d). Values are
  pre-interpolated by Python, never passed as Jinja context, so that second
  parse is pure downside. Eight of the ten page modules now return the string
  directly through a local `_page()`; only `quotation.py` and `product.py`
  still re-render. **Do not add a new `render_template_string` call.**
- User-supplied text is **not** auto-escaped in most places. `address.py` uses
  `markupsafe.escape` via `_e()`; `pipeline.py` uses `esc()`. `quotation.py`
  and `product.py` mostly do not. Treat this as a known gap, not a pattern to
  copy.

---

## 2. Module map

| File | Lines | Role |
|---|---|---|
| [app.py](app.py) | 149 | Wiring only. Boots persistence, registers blueprints, error handlers (404/500/413). Never implements features. |
| [store.py](store.py) | 35 | The `STORE` dict. Single shared object, imported everywhere. |
| [db.py](db.py) | 407 | MySQL persistence by snapshot-and-diff, with per-collection failure isolation. |
| [branding.py](branding.py) | 251 | Company identity, bank details, colour palette, chart palette, logo data URIs. |
| [dashboard.py](dashboard.py) | 1302 | Operations dashboard **+ `BASE_STYLES` and `_nav()` that every other module imports** + the 413 page. |
| [product.py](product.py) | 1347 | Product catalogue + assemblies (BOM). Owns `hsn`, the source of every HSN downstream. |
| [quotation.py](quotation.py) | 2693 | Quotation form + printed document. The big one. |
| [proforma.py](proforma.py) | 1117 | Proforma invoice, derived from a quotation. Reuses the quotation's document sheet. |
| [invoice.py](invoice.py) | 1349 | GST tax invoice, derived from a proforma. Rule 46 document; same sheet again. |
| [purchase.py](purchase.py) | 1369 | **Buy side.** Purchase orders on vendors. Separate pipeline; never touches PI/TI. |
| [spec.py](spec.py) | 1096 | **Specification library.** Clauses of work with *sized variants*. What a BOQ line is written from. **Not a replacement for `product.py`.** |
| [boq.py](boq.py) | 3415 | **Bill of quantities.** The priced schedule for a project. Head of a *second* sell-side chain — see §2b. Owns `line_id`, the key an RA claim matches on. |
| [ra.py](ra.py) | 1922 | **Running Account bills.** Claims against a BOQ revision, with the entry form. Does not yet carry a tax block; required to — see DOMAIN.md §4. |
| [demo_data.py](demo_data.py) | 2795 | **Data only, imports nothing.** The 56 seeded specs and the 97-line demo BOQ, generated from the client's own workbook. |
| `tools/gen_demo_data.py` | 311 | The generator that emits `demo_data.py`. Not imported by the app. **Regenerate, don't hand-edit.** |
| `tools/backfill_line_ids.py` | 99 | One-time migration: mints `line_id` on BOQ lines written before the field. Idempotent; takes `--dry-run`. |
| `fixtures/README.md` | — | Where to put the two client workbooks. **They are gitignored** — see the note there about what is already in the history. |
| [settings.py](settings.py) | 285 | Company identity + bank details form. Writes runtime overrides onto `branding`. |
| [pipeline.py](pipeline.py) | 542 | Sales stages, customer PO, win/loss, **and the app's shared utilities** (`esc`, `parse_money`, `fy_of`, `fy_ref`). Pure logic, no routes. |
| [address.py](address.py) | 951 | Address book + the pickers that quotations and purchase orders use. |
| [extractor.py](extractor.py) | 407 | "Market News" page. **Hardcoded dummy data**, dark theme, decorative. |
| `integration.py` | 131 | **Dead file.** Stale docs only — see §8. |
| `product_view_additions.py` | 495 | **Dead file.** Stale docs only — see §8. |

**Import direction (never reverse these — circular imports):**

```
app.py
 ├─ dashboard.py ──────────────┐  (BASE_STYLES, _nav) imports branding, store, pipeline, db
 ├─ product.py ────────────────┤  imports dashboard, branding, store
 ├─ address.py ────────────────┤  imports dashboard, branding, store, product (PRODUCT_STYLES)
 ├─ quotation.py ──────────────┤  imports dashboard, branding, store, address, pipeline
 ├─ proforma.py ───────────────┤  imports dashboard, branding, store, pipeline, quotation
 ├─ invoice.py ────────────────┤  imports dashboard, branding, store, pipeline, quotation, proforma
 ├─ purchase.py ───────────────┤  imports dashboard, branding, store, pipeline, quotation, address
 ├─ spec.py ───────────────────┤  imports dashboard, branding, store, pipeline, demo_data
 ├─ boq.py ────────────────────┤  imports dashboard, branding, store, pipeline, quotation, address, spec, demo_data
 ├─ settings.py ───────────────┤  imports dashboard, branding, store, pipeline, quotation
 └─ extractor.py ──────────────┘  imports branding only

pipeline.py  imports nothing from the app  ← keep it that way
branding.py  imports nothing from the app  ← keep it that way
demo_data.py imports nothing AT ALL        ← keep it that way
```

**`demo_data.py` is the third bottom-of-graph module.** It holds the 56 seeded
specs and the 97-line demo BOQ and imports nothing — not `store`, not
`branding`, not even `pipeline` — which is exactly what lets `spec.py` and
`boq.py` both read it with no risk of a cycle. It is separate from those two
because of scale, not taste: inline, it would leave `spec.py` more data than
code and push `boq.py` past 2700 lines. `product.py`'s twelve inline seed rows
are a different order of thing and are fine where they are.

It is **generated, not written**: `python tools/gen_demo_data.py` reads
`sify_boq.xlsx` and emits it, byte-for-byte reproducibly. Clause text, rates,
quantities and variant sets are read mechanically; only each spec's short
title, code and category are a human judgement, and those live in
`tools/curation.py` keyed by the row that defines the clause. **Regenerate
rather than hand-editing** — a hand edit is lost the next time anything else
changes. `tools/` is not imported by the app and `sify_boq.xlsx` is only needed
to re-run it, never at runtime.

`quotation.py → pipeline.py`, **never** the reverse.

**The document chain imports strictly downstream:**

```
quotation.py  ←──  proforma.py  ←──  invoice.py
```

`proforma.py → quotation.py`, **never** the reverse. proforma imports the
document's formatters and stylesheet (`_inr`, `_fmt_qty`, `_amount_in_words`,
`_meta`, `VIEW_DOC_STYLES`, `QUOTATION_STYLES`) so the two documents cannot
drift apart. The quotation view page links *to* proforma with
`url_for("proforma.…")` and reads `STORE["proformas"]` directly — a `url_for`
string needs no import, which is what keeps the arrow one-way.

`invoice.py → proforma.py → quotation.py`, and **never** the reverse of either.
invoice imports the same document formatters from `quotation`, plus
`PROFORMA_STYLES` and `_sel_keep` from `proforma`. The proforma view page links
*to* the tax invoice with `url_for("invoice.…")` and reads `STORE["invoices"]`
directly — exactly the same trick, one link further down.

**Where a shared CSS rule lives follows from that.** A class rendered by two
modules belongs to the sheet of the **upstream** one, because the downstream
module already loads it and the upstream one cannot import back:

| Class | Defined in | Rendered by |
|---|---|---|
| `.pi-chip` / `.pi-strip` | `QUOTATION_STYLES` | quotation deal panel, proforma |
| `.ti-chip` / `.ti-strip` | `PROFORMA_STYLES` | proforma view page, invoice |
| `.jc-*` / `.po-chip` / `.po-strip` | `QUOTATION_STYLES` | quotation deal panel, purchase |

**The buy side imports the sell side's document toolkit, and nothing else.**

```
purchase.py ──► quotation.py     the A4 sheet + formatters, NOT the sales chain
purchase.py ──► address.py       the vendor picker
purchase.py ──► pipeline.py      fy_of / fy_ref / esc / parse_money
```

`purchase.py` must **never** import `proforma.py` or `invoice.py`, and none of
those may import it. `quotation.py` renders the job-costing block by reading
`STORE["purchases"]` directly plus `url_for` — the same one-way trick used
twice already on the sell side.

**Every one of those directions is now actually tested** —
[tests/test_import_directions.py](tests/test_import_directions.py) parses each
module's AST and asserts the arrow. Until the BOQ chain was added this file
claimed a test existed when none did; the suite is real now (`python -m pytest
tests/`). It distinguishes a **module-level** import from one inside a function
body, because `dashboard.index()` deliberately imports the seeders in the
function body and a check that could not tell them apart would flag the
documented design as a violation.

### 2b. The BOQ chain — a second sell-side chain, not a fourth link

```
SELL SIDE   quotation ──► proforma invoice ──► tax invoice     goods, invoiced in lots
            BOQ ──────► RA bill 1 ──► RA bill 2 ──► …          a project, billed as it is built
BUY SIDE    purchase order ──► [vendor lifecycle]
```

A **quotation** is an offer to sell goods, priced per line and invoiced once or
a few times against the whole. A **BOQ** is the priced schedule of a *project*:
one to two hundred lines, grouped into systems (sections A/B/C…), each line's
quantity broken down by the area or floor it is installed on, and each line
priced **twice** — once to supply the material and once to install it. It is
billed progressively through Running Account bills as the work is executed.

That is why it is a separate chain rather than a render mode of the quotation:
the unit of progress is a **quantity on a line**, not a share of a document
total, and no field on a quotation can carry that.

```
boq.py ──► quotation.py     the A4 sheet + formatters, NOT the sales chain
boq.py ──► address.py       the customer picker
boq.py ──► pipeline.py      esc / parse_money / fy_of / fy_ref
boq.py ──► spec.py          the specification library — the line picker
boq.py ──► demo_data.py     seed data only

spec.py ──► dashboard, branding, store, pipeline, demo_data
```

`boq.py` must **never** import `ra.py`, `proforma.py`, `invoice.py` or
`purchase.py`. The BOQ view page links out to RA bills with `url_for` and reads
`STORE["ra_bills"]` directly — the same one-way trick, now used four times.
A BOQ has no proforma, and it does not link to a purchase order.

**`ra.py` exists as of Phase 4 step 1** — record shape, the revision chain and
the over-claim block, with no routes yet. The arrow runs one way:

```
ra.py ──► boq.py        the schedule a claim is measured against, plus
                        _line_id / _item_no / _num / _fmt_qty / BOQ_STYLES
ra.py ──► quotation.py  QUOTATION_STYLES + _inr — the form widgets, so the RA
                        form IS the BOQ form. NOT _tax_lines (see below).
ra.py ──► dashboard.py  BASE_STYLES / _nav — the persistence strip comes free
ra.py ──► pipeline.py   esc / parse_money / fy_of / fy_ref
ra.py ──► store, branding
```

and it must **never** import `proforma.py`, `invoice.py`, `purchase.py`,
`product.py` or `spec.py`. The `invoice.py` prohibition is the load-bearing one:
**the RA bill's tax block is per-line and carries HSN/SAC, while the sell chain's is document-level**,
and sharing that machinery would couple two chains that were deliberately built parallel. All of these are asserted in
[tests/test_import_directions.py](tests/test_import_directions.py).

✅ **Closed at step 2.** `/boq/view/<id>` used to 500 once an `ra_bills` record
existed, because boq.py builds `url_for("ra.view_ra", …)` and no `ra` blueprint
was registered. `app.py` now registers it, and
`test_boq_view_renders_when_an_ra_bill_exists` fails with that same
`BuildError` if it is ever unregistered.

**`boq.py` must not import `product.py` either**, and `spec.py` must never
import `boq.py`. The BOQ picker reads the *spec library*: `product.base_price`
is what we sell a unit of stock for and is not a BOQ supply rate.

**`pipeline.py` is where a helper goes when both pipelines need it.** It already
held `esc` and `parse_money`; `fy_of` and `fy_ref` joined them when the PO
series needed the same financial-year numbering as the tax invoice. It imports
nothing from the app, so it is the only place a shared helper can live without
coupling buy side to sell side.

**dashboard.py may import `branding`, `store`, `pipeline` and `db`** — none of
those import anything from the app, so there is no cycle. `db` is on that list
because `_nav()` renders the persistence-failure strip (§4) and `_nav()` is the
only thing in this app that is on every page; db.py imports pymysql, dotenv and
the standard library and nothing of ours, so it sits at the bottom of the graph
beside branding.py and pipeline.py. dashboard.py must **never** import
`product`, `quotation` or `address` at module level, because those import *it*.
`index()` pulls `ensure_demo_products` / `ensure_demo_addresses` in **inside the
function body** for exactly that reason; that is deliberate, not an oversight.

---

## 3. Data model

`store.py` exposes one module-level dict. Because Python caches modules, every
blueprint holds the **same object**, so in-place mutation is visible everywhere:

```python
STORE = {
    "products":     {},     # uuid -> product
    "quotations":   {},     # uuid -> quotation
    "proformas":    {},     # uuid -> proforma invoice
    "invoices":     {},     # uuid -> GST tax invoice
    "purchases":    {},     # uuid -> purchase order   (BUY side)
    "specs":        {},     # uuid -> specification library entry (clause + variants)
    "boqs":         {},     # uuid -> bill of quantities (head of the BOQ -> RA chain)
    "ra_bills":     {},     # uuid -> Running Account claim against a BOQ revision
    "addresses":    {},     # uuid -> address
    "settings":     {},     # "company" -> branding overrides (a singleton row)
    "_seeded":      False,  # product seeder guard
    "_addr_seeded": False,  # address seeder guard
}
```

### Product

```python
{
  "id": uuid, "name": str, "part_no": str, "hsn": str, "unit": str,
  "base_price": float, "description": str,
  "type": "standalone" | "assembly" | "support",
  "children": [ {"product_id": uuid, "qty": int}, ... ],   # assemblies only
}
```

- `assembly` = has children (a BOM). `support` = a sub-component not sold
  alone. `standalone` = sold on its own. Only the badge and the picker treat
  these differently; nothing enforces that `support` items stay inside
  assemblies.
- **`hsn` is where every HSN on every document comes from.** It is captured on
  the add-product form, validated by `_valid_hsn()` (digits only, 4/6/8 — the
  three lengths GST issues; how many are *required* depends on turnover, which
  this app does not know, so the rule is shape-only), and carried down
  unchanged by `_process_selections()` → `line_items` → PI → tax invoice.
  Optional on the form, **mandatory on a tax invoice** (Rule 46(g)) — a line
  without one costs the customer the input tax credit on it. Blank renders as
  the amber `B.field()` chip in the catalogue and on the printed sheet, never
  as an empty cell.
- `_seed()` **backfills `hsn` onto an existing seeded row when it is blank**,
  and only then. Those twelve rows have fixed UUIDs and predate the field, so a
  database from an earlier run holds them all without one — and with no product
  edit route (§7.2) a user cannot add it by hand. It fills a gap; it never
  overwrites a code someone has set.

#### `product.backfill_line_item_hsn()` — a one-time migration, not app behaviour

Filling `hsn` on the *catalogue* does nothing for documents already issued,
because every document freezes a **copy** of its line items (below). Records
written before the field existed would therefore stay blank forever, and a tax
invoice raised from such a proforma prints an amber chip on every line.

`backfill_line_item_hsn()` walks `quotations`, `proformas` and `invoices` and
fills a blank `hsn` from the catalogue, matching on **part_no** (the stable key
— a line item does not record the product id, and names get edited). It is
**deliberately not called at boot.**

It drives through the freeze, which is only defensible because:

- it fills a field that **did not exist** when those rows were written, so no
  agreed value is overwritten;
- it **only ever fills a blank** — a code already present, even one that
  disagrees with today's catalogue, is left alone;
- it touches nothing carrying a commercial agreement: name, qty, unit, price,
  total and depth are untouched.

**Applied once to the working database** (4 quotations, 2 proformas — 31 rows
filled). Run it again only after adding HSN to catalogue rows that older
documents were built from. Never wire it into startup: once a classification is
*corrected*, pushing that correction onto issued documents is exactly the
rewriting the freeze exists to prevent.

### Quotation

~50 flat keys written in one literal at [quotation.py:1063](quotation.py#L1063).
Groups:

- **Identity:** `id`, `ref` (`QT-0001`), `date`, `amend_no`, `rate_contract`
- **Deal meta:** `qtn_type`, `validity_days`, `buyer_ref`, `other_ref`,
  `lead_source`, `lead_type`, `lead_subtype`, `lead_owner`, `exp_closing`,
  `region`, `assigned_to`, `company_branch`, `auth_signatory`
- **Customer:** `account_name` (**the only required field**), `contact_person`,
  `bill_*` (addr/country/state/city/pin/phone/gstin), `ship_same`, `ship_*`
- **Commercial terms:** `incoterms`, `payment_terms`, `delivery_terms`,
  `delivery_date`, `dispatch_through`
- **Money:** `tax_type`, `cgst_rate`/`sgst_rate`/`igst_rate`/`vat_rate`,
  `tax_info`, `subtotal`, `grand_total`, `total_qty`
- **Content:** `selections` (raw JSON from the browser), `line_items` (flattened
  rows for printing), `to` (pre-joined multi-line address block)
- **Pipeline** (added by `pipeline.ensure_fields`): `sales_stage`, `po_number`,
  `po_date`, `po_value`, `lost_reason`, `stage_history[]`

A `line_item` row:

```python
{"type": "assembly"|"item", "name", "part_no", "hsn",
 "qty": float, "unit", "price": float, "total": float,
 "depth": 0 | 1}
```

**Only two depths exist.** `depth 0` = a product the user added; `depth 1` = one
of its components. There is no recursive expansion at quotation time — the
browser-side JS flattens the tree before POST. (`integration.py` documents a
recursive `expand_product()` engine; **that engine does not exist**. See §8.)

### Proforma Invoice

Written in one literal in `proforma.create_proforma()`. It is **derived from a
quotation, never entered from scratch** — there is no blank-PI form and there
should not be one.

- **Identity:** `id`, `ref` (`PI-0001`), `date`
- **Back-link:** `quotation_id`, `quotation_ref`, `quotation_date`
- **Customer:** copied from the quotation — `account_name`, `contact_person`,
  `to`, `bill_gstin`, `ship_same`, `ship_*`
- **Frozen content:** `line_items` (a **copy**, `[dict(r) for r in …]`),
  `subtotal`, `tax_type`, `tax_info`, `grand_total`, `total_qty`
- **The invoice's own fields:** `po_number`, `po_date`, `advance_pct`,
  `amount_due`, `balance_due`, `payment_terms`, `delivery_terms`,
  `delivery_date`, `dispatch_through`, `incoterms`, `validity_days`, `notes`,
  `company_branch`, `auth_signatory`
- **The running position, frozen at issue:** `prior_invoiced` (float — the sum
  of `amount_due` over every PI already raised against the same quotation when
  this one was created) and `prior_refs` (`["PI-0001", …]`, those PIs' numbers).

Four properties this shape exists to guarantee:

1. **The snapshot is frozen.** `line_items` is copied, not referenced. A
   shallow `dict(row)` per line is sufficient — every value in a `line_item` is
   a scalar. Editing the source quotation afterwards cannot reach an issued
   invoice, which is the whole reason a PI is its own record.
2. **`quotation_ref` is stored, not looked up.** The PI still prints correctly
   as a historical document if the quotation is ever removed.
3. **`prior_invoiced + amount_due + balance_due == grand_total`**, always.
   `amount_due` is the figure the customer actually has to pay now;
   `advance_pct` is only how it was derived, and it is always a share of the
   **quoted value**, never of the balance — that is what "30% advance" means in
   the trade and what prints on the document.
4. **`prior_invoiced` is frozen too, and never recomputed at render time.**
   PI-0001 stated a balance that was true on its date; raising PI-0002 must not
   rewrite a document already in the customer's ledger. So `balance_due` is
   `order − invoiced *before* this one − this one`, and a later PI cannot reach
   back into an earlier one.

Many PIs may point at one quotation (advance, then balance, then a part
supply), which is why the running position is part of the record. Amounts that
together **exceed** the quoted value are still permitted — scope grows, prices
move — but take a deliberate confirmation (§5). Both fields default to `0.0` /
`[]` when absent, so PIs written before they existed render exactly as before.

⚠ **Invoiced, not received.** Nothing in this app records payment. Every figure
here is what has been *asked for*. It keeps the paperwork self-consistent; it is
not a receivables position.

### Tax Invoice

Written in one literal in `invoice.create_invoice()`. **Derived from a proforma
invoice, never entered from scratch** — there is no blank-invoice form and
there should not be one.

- **Identity:** `id`, `ref` (`SF/TI/26-27/0001`), `fy` (`26-27`), `date`
- **Back-links:** `proforma_id`, `proforma_ref`, `proforma_date`,
  `quotation_id`, `quotation_ref` — both refs **stored, not looked up**, so the
  invoice still prints as a historical document if either source is removed
- **Customer:** copied from the PI — `account_name`, `contact_person`, `to`,
  `bill_gstin`, `ship_same`, `ship_*`
- **Frozen content:** `line_items` (a **copy**, `[dict(r) for r in …]`),
  `subtotal`, `tax_type`, `tax_info`, `grand_total`, `total_qty`
- **Statutory — the fields this document is the first in the chain to carry:**
  `place_of_supply`, `pos_code` (its GST State code), `reverse_charge` (bool)
- **Settlement:** `advance_received`, `net_payable`
- **Movement of the goods:** `po_number`, `po_date`, `dispatch_through`,
  `dispatch_doc_no` (LR/docket), `vehicle_no`, `eway_bill_no`
- **Other:** `payment_terms`, `notes`, `company_branch`, `auth_signatory`

Four properties this shape exists to guarantee:

1. **The snapshot is frozen**, exactly as the PI's is and for the same reason —
   a shallow `dict(row)` per line, because every value in a `line_item` is a
   scalar.
2. **`advance_received + net_payable == grand_total`**, always. The tax invoice
   is raised for the **full value of the goods supplied**; what was already paid
   against the PI is shown as an adjustment, not deducted from the invoice
   value. Charging GST on a reduced figure because an advance was received is
   the mistake this shape is built to prevent.
3. **`ref` is unique within `fy`, not globally.** Rule 46(b) requires
   uniqueness per financial year and ≤ 16 characters; the series restarts at
   `0001` each 1 April. `fy` is stored so the register can group without
   re-parsing dates.
4. **`pos_code` is stored alongside `place_of_supply`**, not derived at render
   time, so the printed document does not depend on `GST_STATE_CODES` never
   being edited.

Many tax invoices may point at one PI — a part supply is invoiced in lots. The
convert form lists those already raised, and the PI view page carries them as
`.ti-chip` links, so issuing a second one is a decision rather than an accident.

### Purchase Order  (buy side)

Written in one literal in `purchase.create_purchase()`. Unlike every sell-side
document it is **entered from scratch, not derived** — there is no upstream
record to freeze a copy of, because the decision to buy is ours.

- **Identity:** `id`, `ref` (`SF/PO/26-27/0001`), `fy`, `date`
- **Vendor — who we buy FROM, not a customer:** `vendor_id`, `vendor_name`,
  `vendor_gstin`, `to` (the printable block), `vendor_ref` (their offer no.)
- **Soft job link:** `quotation_id`, `quotation_ref` — **both may be `""`**
- **Content:** `line_items`, `subtotal`, `tax_type`, `tax_info`,
  `grand_total`, `total_qty`
- **Where and when:** `delivery_date` (wanted by), `delivery_to`,
  `payment_terms`, `delivery_terms`, `dispatch_through`, `incoterms`
- **Lifecycle:** `status`, `status_history[]` (`{at, status, note}`)
- **Other:** `notes`, `company_branch`, `auth_signatory`

Four things that differ from the sell side and are easy to get wrong:

1. **The line items are NOT frozen from anything** — they are typed on the
   form. There is no snapshot contract here because there is no source
   document; the PO *is* the source.
2. **`line_items` is flat: `depth` is always 0 and assemblies are not
   expanded.** We buy the thing the vendor sells us. If the components are
   bought separately they are separate lines, chosen deliberately. That is the
   exact opposite of the quotation, where a BOM is expanded so the customer can
   see what is inside.
3. **The tax is input tax we pay**, not output tax we collect. It uses the same
   `quotation._tax_lines()`, but it sits on the other side of the ledger.
4. **`quotation_id` may be empty and that is normal** — a stock purchase. Any
   code walking purchases must not assume a job.

### Specification (the library a BOQ is written from)

```python
{"id": uuid, "code": "PIPE-MS-C-1239-AG",
 "title": "MS heavy duty 'C' class pipe, IS 1239 / 3589 — above ground",
 "spec_text": str,          # the full clause; becomes the BOQ line description
 "category": "Piping",      # Piping|Valves|Sprinklers|Hydrant|Pumps|Panels|Civil|Other
 "supply_hsn": "73063090", "install_sac": "995462",
 "supply_gst_rate": 18.0,  "install_gst_rate": 18.0,
 "variants": [
   {"label": "150 mm dia", "dimension": "150", "dim_unit": "mm",
    "unit": "Mtrs",
    "default_supply_base_rate": 1760.0,
    "default_install_base_rate": 1200.0},
   ...]}
```

**This is not `product.py` and does not replace it.** `product.py` serves the
quotation → PI → tax invoice chain, which is live business. An entry there is a
*thing we sell* at one `base_price` with a BOM; an entry here is a *clause of
work* with a supply rate and an installation rate.

Five properties this shape exists to guarantee:

1. **`variants` is always a list and never null.** An unsized item — a flow
   switch, a liaisoning charge — carries **exactly one** variant with an empty
   label and no dimension, so every consumer has one code path instead of two.
   Enforced at save in `_clean_variants()`, not left to the caller.
2. **The variant model is the point.** BOQ item 24 is one paragraph of
   specification and 24.a–24.i are that clause at nine sizes, each with its own
   rate and unit. `product.children` is a bill of materials and cannot express
   that.
3. **The rates are defaults and only ever *suggested*.** They fill an empty box
   on the BOQ form and never overwrite a typed one — `purchase.fillRate()`'s
   precedent. The BOQ stores what was entered.
4. **Escalation percentages deliberately do not live here.** An escalation
   belongs to a *project*; on the library it would make one job's negotiation
   look like a property of the material.
5. **`spec_text` is COPIED onto a BOQ line, never referenced**, which is why a
   line item carries no `spec_id` — and why `delete_spec()` needs no dependency
   guard. See §5's `/spec` section.

### Bill of Quantities

Written in one literal in `boq.create_boq()`. **Entered from scratch**, like a
purchase order and unlike every other sell-side document — there is no upstream
record to freeze a copy of, because the schedule is the source.

- **Identity:** `id`, `ref` (`SF/BOQ/26-27/0001`), `fy`, `date`, `rev_no`
- **The project:** `project_name`, `site_location`
- **Customer:** `account_name` (usually a main contractor), `contact_person`,
  `to`, `bill_gstin`, `ship_same`, `ship_*`
- **Pricing basis:** `rate_basis_label` — what the base-rate column is headed
  on the printed sheet. These schedules are commonly priced off a rate contract
  agreed on *another* project ("Mohali Rates") and then escalated, so the label
  is per-BOQ data rather than a constant.
- **Structure:** `sections` — `[{code, title, areas: [...]}]`
- **Content:** `line_items`
- **Money:** `supply_subtotal`, `install_subtotal`, `subtotal`
- **Revision link:** `supersedes` — the previous BOQ id this one replaces, or
  `""` for an original. A revision is a **new record**, never an edit, because
  RA bills are measured against a specific revision and an issued claim's basis
  must not move. `ra.py` walks this to sum claims across the chain. Nothing
  writes a non-empty value yet; the revision route is not built.
- **Other:** `payment_terms`, `delivery_terms`, `notes`, `company_branch`,
  `auth_signatory`

A `line_item` row:

```python
{"line_id": "a3f19c0b7e42", # opaque, server-minted — THE KEY A CLAIM MATCHES ON
 "item_no": "24.b",          # STRING, always — a DISPLAY LABEL, never a key
 "parent_item_no": "24",     # "" for top level
 "section": "B",
 "is_header": False,         # True = specification paragraph, no qty or rate
 "description": str,         # up to ~1500 chars
 "remark": str,              # their internal note column — captured, not printed
 "unit": "Mtrs",
 "area_qty": {"T1": 700.0},  # keys are a subset of the SECTION's areas
 "total_qty": 700.0,
 "supply_base_rate": 1760.0, "supply_escalation_pct": 15.0,
 "supply_rate": 2024.0, "supply_amount": 1416800.0,
 "supply_hsn": "73090090", "supply_gst_rate": 18.0,
 "install_base_rate": 1200.0, "install_escalation_pct": 0.0,
 "install_rate": 1200.0, "install_amount": 840000.0,
 "install_sac": "995461", "install_gst_rate": 18.0}
```

Eight properties this shape exists to guarantee:

0. **`line_id` is what an RA claim is matched on, and `item_no` never is.**
   It is opaque, minted by `boq._new_line_id()` (12 hex characters off
   `uuid4`), unique **within one BOQ record** — claims are always scoped to a
   parent BOQ, so there is deliberately no global registry — and nothing
   outside the code ever reads it. It is not shown on the form, not printed,
   and not part of any reference the client quotes back.

   It exists because `item_no` cannot do the job and never could. Item numbers
   **restart per section** (item `4` is in both A and B) and the client's own
   section A carries item `17` **twice**, on a flexible sprinkler drop at
   ₹1,800 and a 150 mm butterfly valve at ₹14,572.50. Keying the over-claim
   guard on `item_no` collapsed 87 priced lines into 77 entries, which waved
   **₹1,99,122.50** of over-claim through and refused **₹84,071.00** of
   legitimate claim, on the client's real schedule. It is also **not
   positional**: an index would re-attribute every claim below any inserted
   line, and not derived from any displayed field, because a key made of
   editable text re-attributes claims the moment somebody fixes a typo.

   ⚠ **The round trip is the fragile part.** `_clean_lines()` builds a fresh
   dict from named keys by construction, so an id that is not explicitly
   carried across is **dropped and re-minted on the next save**, which orphans
   every claim against that BOQ with no error anywhere. The editor posts
   `line_id` per line and `_clean_lines()` preserves it; four paths are
   defined and each is tested in
   [tests/test_boq_line_ids.py](tests/test_boq_line_ids.py):

   | posted id | what happens |
   |---|---|
   | present, well-formed, unused | kept **verbatim** |
   | missing or empty | minted — this is a new line |
   | duplicated within one post | first kept, the rest minted (a copy-pasted row) |
   | malformed | minted; never trusted, never echoed |

   `boq.backfill_line_ids()` is the one-time migration for records written
   before the field, driven by `tools/backfill_line_ids.py`. It only ever fills
   a blank and is idempotent. It **cannot repair RA claims** that predate the
   field and does not try — matching one back would have to guess through
   `item_no`, which is ambiguous on exactly the lines that matter — so it
   counts and reports them instead.

1. **`item_no` is a STRING, everywhere, always.** The client's workbooks store
   item 4.1 as `4.0999999999999996`, 4.4 as `4.4000000000000004` and 4.6 as
   `4.5999999999999996`. A float that reaches the document prints either the
   wrong number or seventeen digits of binary noise beside a quantity somebody
   is paid against. `boq._item_no()` is the guard.
2. **`parent_item_no` is a SPECIFICATION hierarchy, not a BOM depth.** A header
   line carries the specification and no quantity; the lines under it carry the
   quantities and the rates. This is deliberately **not**
   `line_item["depth"]` — that means "component of an assembly", and the two
   collide the first time a BOQ line is itself an assembly.
3. **Areas belong to the SECTION, not to the BOQ.** The client's own workbook
   declares `External` + `L0` for section A, `T1` for section B, and none at
   all for section C. `area_qty` keys are a subset of that line's *section's*
   areas; a section may declare none, and then `total_qty` stands alone with
   nothing to reconcile it against.
4. **A line may be supply-only or installation-only.** Section C is
   installation-only; four lines in section B are nil-priced (a quantity, no
   rate, amount 0) and are valid. Never assume both tracks are populated.
5. **`supply_rate` is derived on entry but STORED, and stored AS ENTERED.**
   The printed document must not depend on the escalation never being edited —
   the same principle as `pos_code` on the tax invoice. And it is never
   recomputed from `base × (1 + pct)`, because the client's own sheets carry a
   dozen lines where the agreed rate deliberately differs (a tamper switch at
   ₹2000/nos, a larger diameter at the Bangalore site). Reporting that
   disagreement is the importer's job; resolving it is nobody's.
6. **A `None` base rate is not zero.** It means the rate was negotiated
   directly rather than escalated — the `-` in the client's cell — and it
   prints as `-`. Collapsing it to 0.0 would state that the material is free.
7. **Section subtotals are COMPUTED from `line_items`, never stored.** Only the
   BOQ-level trio is stored, for the register and the dashboard card, and the
   document recomputes even those so a printed sheet can never contradict its
   own lines.

### RA Bill  (Running Account claim)

Written by `ra.py`. Progressive claim against a specific BOQ revision, carrying a tax block per DOMAIN.md §4 (headed TAX INVOICE). Does not import `quotation._tax_lines()` nor `invoice.py` (asserted by `tests/test_ra_record.py`).

- **Identity:** `id`, `ref` (`SF/RA/26-27/0004`), `fy`, `date`, `tax_invoice_ref`, `tax_invoice_date`, `po_ref`, `po_date` (`po_ref` & `po_date` default to previous bill for same BOQ; stored as known duplication)
- **Back-link:** `boq_id` (a **specific revision**), `boq_ref`, `boq_rev_no` — refs stored, not looked up
- **Position in the run:** `ra_no` (int, sequence within project), `leg` ∈ `supply | installation`
- **Copied from BOQ at issue:** `project_name`, `site_location`, `account_name`, `contact_person`, `to`, `bill_gstin`
- **Content:** `claims` (each claim row snapshots `hsn_sac` and `gst_rate` from BOQ line)
- **Money & Tax:** `claim_subtotal`, `deductions[]`, `deduction_total`, `net_payable`, `tax_type`, `cgst_rate`, `sgst_rate`, `igst_rate`, `cgst_amount`, `sgst_amount`, `igst_amount`, `tax_amount`, `rounding_off` (computed delta), `grand_total` (frozen at save)
- **Certification:** `status` ∈ `draft | submitted | certified`, `certified_on`
- **Other:** `notes`, `company_branch`, `auth_signatory`

A `claim` row:

```python
{"line_id": "a3f19c0b7e42",   # THE MATCH KEY, copied off the BOQ line
 "item_no": "24.b",           # the display label; not unique, never matched on
 "section": "B", "description": str, "unit": "Mtrs",
 "approved_qty": 700.0, "approved_rate": 2024.0,   # frozen at issue
 "prev_qty": 120.0,                                 # cumulative BEFORE this bill
 "qty": 80.0, "rate": 2024.0, "amount": 161920.0,
 "balance_qty": 500.0, "rate_varies": False,
 "certified_qty": None, "certified_rate": None}   # None = NOT YET certified
```

Six properties this shape exists to guarantee:

0. **`line_id` is the key, `item_no` is the label.** Stored on the claim so the
   cumulative sum survives the line's item number being edited, or renumbered
   by a later revision. A claim row carrying **no** id matches nothing and is
   skipped rather than falling back to `item_no` — a fallback would resurrect
   the collapse the key exists to end, on precisely the ambiguous lines, and
   would do it silently.

1. **The figures are frozen.** `approved_qty`, `approved_rate`, `prev_qty` and
   `balance_qty` are stored, never recomputed at render. RA3 stated a balance
   that was true on its date and issuing RA5 must not rewrite a document the
   client has already certified — exactly `proforma.prior_invoiced`'s rule.
   **The guard at entry uses live figures; the document uses frozen ones.**
2. **`rate` is stored as entered and may disagree with `approved_rate`** — it
   does on ten cells of the client's own annexure, because rates legitimately
   move on approved variations. So it **warns and never blocks**, and
   `rate_varies` is a stored fact about the issued bill rather than a
   re-derivation. A rate silently disagreeing with the approved BOQ is one of
   the two failure modes this module was sold to catch.
3. **`deductions` is bill-level and exists from day one, empty.** Retention,
   mobilisation-advance recovery and cess all fit one shape
   (`{code, label, basis, pct, amount}`). `amount` is **always stored** —
   computed once from `pct × claim_subtotal` when the basis is a percentage —
   so a certified bill cannot change its own figures when a constant moves.
4. **`net_payable == claim_subtotal − deduction_total`, always**, including on
   every bill with an empty deductions list.
5. **`ra_no` is unique across the whole REVISION CHAIN**, not per record, so a
   revision cannot restart the client's sequence at RA1. It is assigned by the
   server and never typed, which is what makes "RA5 before RA4" and "two RA6s"
   *impossible* rather than merely rejected — there is no input to reject.

#### The over-claim block

**A cumulative claim across every RA bill must not exceed the approved BOQ
quantity for that line.** It is a hard block with **no override anywhere in the
UI**; `ra.OVERCLAIM_TOLERANCE` is the only dial and defaults to `0.0`, where the
behaviour is exactly a hard block. When non-zero it applies to the **cumulative**
claim and never per bill — 1% per bill compounds to 9% across the client's nine
RA runs and becomes the over-claim it exists to prevent.

Separately, and not a commercial tolerance: the comparison rounds at `1e-6` so
that `1.1 + 2.2 + 8.7 == 12.000000000000002` is not reported as an over-claim of
two femtometres against an approved 12.

#### The revision chain

Because the block is hard, a **BOQ revision** is the only way through it when
the approved schedule genuinely changes — a new BOQ record carrying
`supersedes`, never an edit, so an issued claim's basis cannot move under it.

`ra.claimed_by_line()` therefore sums **across the whole chain**, and that is
the subtlest requirement in the module: without it a revision resets every
line's claimed quantity to zero and the block guards nothing. It is **derived,
not stored** — a maintained counter must be updated on every create, revision
and delete, and any path that misses one leaves the guard silently wrong, which
is worse than no guard because it is trusted. It costs a pass over ~620 claim
rows at the client's volume and stays cheap to ~50,000, about 80× that.

`approved_by_line()` reads the **latest** revision, because a revision exists
precisely to change what is approved.

Both key on **`line_id`**, not `item_no` — see §3's property 0 for the ₹2.8
lakh that keying on the item number cost on the client's own schedule.

#### What a revision may and may not do to a line

A revision posts the previous revision's lines **with their ids**, so a
surviving line keeps its id through the ordinary `_clean_lines()` round trip
and a genuinely new line mints one. That is the whole point of the identifier:
an RA bill raised against revision 1 still matches its lines after revision 2,
**even if every item number moved**. This retires the restriction the design
recorded at §6.5 — a revision may now renumber freely.

What still needs a guard is **deletion**. `boq.revision_blockers()` refuses to
drop a line that already carries a claim, naming the line and the RA numbers
that claimed it: deleting it leaves a claim with no approved quantity behind
it, so the balance arithmetic has nothing to hold and a bill already submitted
to the main contractor becomes unbacked. If the work genuinely is not
happening, the correction belongs in a claim, not in the schedule the claim was
measured against. Deleting an **unclaimed** line stays free.

It is a **pure function taking the claim map as an argument**, and that is an
import-direction decision rather than a stylistic one: `boq.py` may never
import `ra.py`, so `ra.claims_by_line_id()` builds the map and the caller
passes it in. The revision route itself is not built yet.

#### Two edit permissions on one record

The claim freezes. The certificate never does. They are separate questions and
`ra.py` answers them separately, because in the real world **certification
lags** — RA3 comes back certified after RA6 has been raised, and a certificate
frozen with its claim would be unusable exactly when it is needed.

| | Gate | Rule |
|---|---|---|
| **The claim** (`qty`, `rate`, `amount`) | `claim_is_frozen()` | editable **only while it is the latest bill** for its BOQ |
| **The certificate** (`certified_qty`, `certified_rate`, `status`, `certified_on`) | none | editable **always**, including on a frozen bill |

`claimed_by_line()` sums the whole chain, so editing a mid-chain bill silently
changes every downstream balance — including ones already printed and handed to
the main contractor. Latest-only bounds the recompute to one bill and keeps
printed history true.

`apply_certification()` writes **only** the certified pair, the status and the
date. It never touches `qty`, `rate` or `amount`, which is what makes
"certifying a frozen bill does not reopen its claim" true by construction
rather than by a check.

#### Certification — four rules, each a test

1. **The over-claim block runs on CLAIMED quantity, never on certified.** You
   cannot claim beyond the BOQ; what the contractor then certifies is his
   decision, not a validation input.
2. **Uncertified is NOT zero.** `None` means "not yet ruled on" — excluded from
   certified totals entirely and reported as *n of m*. Summing a blank as zero
   under-reports receivables, the exact inverse of the error this system was
   sold to catch. A certified quantity of **0.0 is a ruling** and does count;
   the two must not collapse into each other.
3. **Certified above claimed WARNS, never blocks** — the same treatment the
   rate divergence gets, and for the same reason.
4. **Deleting a bill carrying any certification data is refused**, with the
   reason shown rather than the button hidden. It has been out of the building
   and acknowledged; deleting it destroys the only record of what was allowed
   against what was claimed.

The **entry UI** for certification is step 3, on the register. Step 2 built the
record shape, the arithmetic and the tests.

#### `item_no` on a claim row is a SNAPSHOT

Taken by `build_claim()` when the claim is made, and never re-derived. A
revision may now renumber freely, so a bill printed last month against item 17
would otherwise silently re-render as item 18 — quietly changing a document
already submitted to the main contractor. The rule:

- **matching** is always on `line_id`;
- **a document** — a record of what was sent — prints the snapshot;
- **a current-state screen** shows the live number, and where the two disagree
  `/ra/view` shows the snapshot with *(now 18)* beside it rather than replacing
  it.

`/ra/view` has always followed this. `/ra/print` — the actual document — did
not until `tests/test_ra_print_immutability.py` was written; see §5's
*"`/ra/print/<id>` reads the RECORD, never the live BOQ"* for what it was doing
instead and what the loop over `boq["line_items"]` cost beyond the item number.

### Address

```python
{ "id", "label", "type", "contact_name", "company",
  "line1", "line2", "landmark", "city", "state", "pincode", "country",
  "phone", "email", "gstin" }
```

`type` ∈ `office | site | billing | shipping | vendor`.
Validated: PIN `^[1-9][0-9]{5}$`, GSTIN full 15-char pattern.

---

## 4. Persistence — how `db.py` works

STORE is a plain dict that every blueprint mutates **in place**. A write-through
wrapper cannot see `STORE["quotations"][qid]["sales_stage"] = "..."` because
only the outermost `__setitem__` is observable. So `db.py` does not intercept
writes — it **snapshots and diffs**.

```
startup     app.py → db.init() → creates DB + tables → db.load_into(STORE)
every req   app.py @teardown_request → db.sync(STORE)
              for each of the 9 collections, INDEPENDENTLY:
                serialise each record → compare to last-written digest
                → upsert changed, delete missing
                → on error: record it, leave the digests alone, carry on
```

- One table per collection (`products`, `quotations`, `proformas`, `invoices`,
  `purchases`, `addresses`, `settings`), each row is
  `id VARCHAR(64) PK, data JSON, updated_at TIMESTAMP`. The **whole record is a
  JSON document** — chosen because quotation shape is still moving and columns
  would mean a migration per field.
- Trade-off: MySQL cannot query *inside* a quotation. When reporting needs it,
  promote hot fields (`ref`, `sales_stage`, `grand_total`) to generated columns;
  the JSON stays authoritative.
- `teardown_request` (not `after_request`) so a half-finished mutation is saved
  even when a view raised.
- `sync()` **never raises**. A persistence hiccup must not turn a working page
  into a 500.

#### `_digests` holds a sha256, not the record

`_digests[collection][id]` is a 64-character hex digest of the record's
canonical JSON, whatever the record's size. It held the **full JSON string**
until this was changed, which meant the process carried a second complete copy
of the entire database purely to answer "did this change?" — a question a hash
answers exactly as well, because `!=` against the current value is the only
operation ever performed on the cached one.

Measured through `db.py`'s own code path, RSS held by `_digests`:

| Store | JSON | before | after |
|---|---|---|---|
| 1 BOQ (57 records) | 128 KB | 176 KB | 258 KB |
| 50 BOQs (106 records) | 3.78 MB | 7.64 MB | **0.96 MB** |
| 200 BOQs (256 records) | 14.96 MB | 30.02 MB | **0.73 MB** |

The one-BOQ row is allocator noise, not a regression — at 57 records the
retained data is 3.6 KB either way and the figure is arenas the interpreter has
not returned to the OS. The change is worth nothing at the seeded size and
worth ~98% as the database grows, which is the shape you would expect.

It also makes the **retry loop** cheap: a permanently failing collection is
re-diffed on every request (above), and comparing 64 bytes is not comparing the
74 KB a demo BOQ serialises to.

**sha256 rather than a faster non-cryptographic hash**: a collision silently
skips a write, which is indistinguishable from data loss and would surface
months later. The hashing is not the bottleneck — the JSON serialisation that
precedes it is, and that was always happening. `_blob`'s `sort_keys` is what
makes the digest stable; without it a dict rebuilt in a different key order
would hash differently and every request would rewrite the whole database.

#### Failure is per-collection, per-request, and visible

Each of the nine collections is written inside **its own** try/except, and a
failure is recorded against that collection in `db._failures` rather than
flipping a global flag. Three properties follow, and each replaces a real
defect:

1. **One collection failing cannot stop the other eight.** All nine used to sit
   in a single `try`, and `COLLECTIONS` order decided the blast radius: `boqs`
   is 7th, so one oversized BOQ took `addresses` and `settings` with it on the
   same request.
2. **A failure is retried on the next request, not fatal until restart.** The
   old code set `_state["ok"] = False` on any exception, and `sync()`'s
   early-return guard then made every later call a no-op — one transient error
   took persistence dark app-wide for the life of the process. The digest cache
   is advanced **only after** the statement that wrote those rows returned, so
   a failed batch still looks changed and the next request retries exactly it.
   Upserts and deletes are both idempotent, so re-running a batch that half
   landed is safe. A dropped connection heals on the next `_conn()` ping.
3. **The user is told.** `failure_note()` renders as a red `.db-down` strip
   under the nav on **every page**, via `dashboard._nav()` — see §5. A `print`
   to stdout is not a signal anyone working in a browser will ever see. The
   strip clears itself the moment a retry lands; nothing has to be dismissed.

`failure_note()` covers **two** conditions, and the difference matters because
the advice differs:

| Condition | `_state["ok"]` | Note | Strip says |
|---|---|---|---|
| a write failed | True | names the affected work, in words | *Every request retries.* |
| MySQL unreachable at boot, `DB_STRICT` off | False | "the database is not connected" | *Restart the app once MySQL is reachable.* |
| `DB_ENABLED=false` | False | **none** | — |

**The note carries no exception text.** `failure_note()` is a plain sentence
naming the user's work — *"Bills of quantities are not being saved. Everything
else is saving normally."* — built from `db.LABELS`, which maps each collection
to what a human calls it. The office staff reading it cannot act on a MySQL
column error, and furniture full of them is furniture people learn to ignore.
`failure_detail()` is the other half: one `table: error` line per failed
collection, which the strip hangs off its `title=` so it costs a hover to read
and still lands in a screenshot. The startup banner and `status()` take the
detail, not the sentence — whoever reads a console is looking after the server.

The boot case is the one `_failures` cannot see on its own: `sync()` returns
early, so no collection ever fails and an empty `_failures` would report that
everything is fine while the app runs entirely in RAM. It is also never
retried, so telling that user to wait would be a lie. `DB_ENABLED=false` is
deliberately silent — a chosen configuration with a startup banner of its own,
and painting every dev run and every test red is how a warning stops being read.

`_state["ok"]` now means "persistence was initialised", set by `init()` and
never cleared by a failing write. `is_live()` answers that question and **not**
"is everything currently saving" — `failures()` / `failure_note()` answer that.
`sync()` returns `{"written", "deleted", "failed"}`, `failed` being the list of
collection names.

Guarded by [tests/test_persistence_isolation.py](tests/test_persistence_isolation.py)
— 19 tests over a fake connection that refuses a *chosen* collection, which is
the one experiment a real MySQL cannot easily be made to run.
- Seed flags are deliberately **not** persisted, so emptying a table refills it.
- Config in `.env` (gitignored; copy `.env.example`): `DB_ENABLED`, `DB_STRICT`,
  `DB_HOST/PORT/NAME/USER/PASSWORD`, `SECRET_KEY`.
- **Ordering dependency:** `load_dotenv()` runs at `import db` in app.py's import
  block, which executes before `app.secret_key = os.getenv("SECRET_KEY", ...)`.
  Don't move the db import below that line.

---

## 5. Page-by-page guide

### `/` — Dashboard · [dashboard.py](dashboard.py)

**Route:** `GET /` → `dashboard.index`

An **operations dashboard, not a menu.** It answers "what is my pipeline worth,
what is stuck, and what moved" before it offers a link anywhere. Top to bottom:

1. **Page head** — title, today's date, `+ New quotation` / `Register`.
2. **Hero band** — one hero figure (**Open pipeline**, the only ≥48px number on
   the page) plus three stat tiles: PO Expected, Won (with recorded PO value),
   Win rate (with a meter).
3. **Open pipeline by stage** — ordinal bar chart over `P.OPEN_STAGES`; each row
   links to `/quotation/?stage=<name>`.
4. **Needs attention** — the work queue (see below).
5. **Quoted value by month** — stacked columns, last 6 months, won/open/lost.
6. **Recent quotations** — last 6, with `P.stage_badge()` so the badges match
   the register exactly.
7. **Module strip** — the old card launcher (9 cards: catalogue, quotations,
   proforma invoices, tax invoices, spec library, bills of quantities, purchase
   orders, address book, market news), now at the foot, carrying live counts
   instead of prose. The strip is
   `auto-fit`, so adding a card needs no layout change. Settings is reached
   from the nav, not from here — it is configuration, not a module you work in.

   The tax-invoice card counts **`net_payable`, not invoiced value** — the
   figure genuinely still owed, after advances already adjusted. Two cards both
   labelled with a headline total would double-count the same money, since a PI
   and its tax invoice describe one supply.

   The purchase card counts **open orders only** (not Received, not Cancelled):
   a received order is a cost already landed, a cancelled one was never a cost.
   Its status strings are matched **literally rather than importing
   `purchase.py`** — `dashboard.py` is imported *by* every module and must stay
   at the bottom of the import graph (§2). If `PO_STATUSES` is ever renamed,
   `_metrics()` is the second place to change.

   ⚠ **The hero figure is still sell-side only.** Open pipeline, the funnel and
   the month columns all describe money coming in; committed spend appears only
   on its card. A dashboard that nets the two sides is a real piece of work and
   deliberately not attempted here.

**Everything is computed in `_metrics()`**, one pass, pure. `P.summarize()` does
the money; this module adds the funnel, the month buckets and the work queue.

#### The work queue — `_attention()`

Four rules, in priority order; a deal is flagged **once**, by its most urgent
reason, so the panel lists *deals* and not warnings. Sorted urgency-first, then
biggest value first inside a tier.

| Priority | Condition | Tone |
|---|---|---|
| 0 | open and `exp_closing` is in the past | critical (red) |
| 1 | open and stage is `PO Expected` | serious (orange) |
| 1 | **won** but `po_number` is blank | warning (amber) |
| 2 | open and no `stage_history` entry for `STALE_DAYS` (21) | warning (amber) |

`STALE_DAYS`, `TREND_MONTHS`, `ATTENTION_LIMIT` and `RECENT_LIMIT` are
module-level constants — tune the dashboard there, not in a branch.

#### Charts — the rules they follow

Colours are **validated, not chosen by eye** (`branding.CHART_*`, §6):

- The funnel is an **ordinal** ramp — one hue (brand navy), stepping light→dark,
  because stage *order* carries meaning. Never recolour it as a categorical set.
- Won / open / lost are **status** colours, because they mean good/neutral/bad,
  and every one ships with its word in the legend — colour never carries the
  meaning alone.
- Column segment heights are **absolute px against `PLOT_H`**, not percentages,
  so the 2px surface gaps between segments cannot compress a bar and misstate a
  value. A non-zero segment has a 3px floor; a **zero** stage draws no mark at
  all (`.fn-bar`'s 2px `min-width` would otherwise put a tick on an empty stage).
- Values are direct-labelled, so no figure is hover-only; the month tooltip is
  an enhancement and the register is its table view.

#### Degrading honestly

- **No quotations at all** → `_insight_html()` returns a single onboarding panel.
  Six charts of zero make a working app look broken.
- **Counts but no money** → the funnel scales by deal count instead, and the
  panel subtitle says so.
- **Malformed dates / missing fields** → `_pdate()` returns `None` rather than
  raising. A hand-edited record must not be able to 500 the landing page.
- Account names go through `P.esc()` here, unlike most of `quotation.py` (§7.7).

#### This file is also the app's stylesheet

`BASE_STYLES` (reset, nav, `.card`, `.btn`, `.alert`, footer, 580px breakpoint)
and `_nav()` are imported by `product.py`, `quotation.py` and `address.py`. **A
change to `BASE_STYLES` changes every page.** Dashboard-only rules belong in
**`DASH_STYLES`**, which is layered after it and loaded on this page only.
Module-specific CSS is layered *after* `BASE_STYLES` in each module
(`PRODUCT_STYLES`, `QUOTATION_STYLES`, `VIEW_STYLES`, `P.PIPELINE_STYLES`).

`DASH_STYLES` is a **plain string, not an f-string**, so its CSS braces are
written once — only the HTML f-strings below it need doubling.

##### `_nav()` carries the two app-wide warnings

Both ride in `_nav()` for the same reason: it is the only surface that is
genuinely on every page, so a user working inside `/boq/create` for an hour
without loading `/` still sees them. Both clear themselves; neither is
dismissable.

| | Signal | Means | Colour |
|---|---|---|---|
| `.nl-dot` | 7px dot on the Settings link | a company or bank field is blank | amber `--saffron` |
| `.db-down` | full-width strip under the nav | **a collection is not persisting** (§4) | red `--brand` |

The severity gap is deliberate. Amber in this app means *incomplete but
working* — a blank GSTIN prints a chip and the document still goes out. The
strip means *nothing you type is being saved*, and a dot cannot carry that.

`_persistence_strip()` escapes **both** halves with `P.esc`: MySQL quotes the
offending value back in a truncation or duplicate-key message, so user input
reaches both strings, and the detail lands in an *attribute*, where a bare `"`
is what breaks out rather than a `<`. `P.esc` is `html.escape` at its default
`quote=True`, which is what makes it safe there. Its CSS lives in
`BASE_STYLES` (it is on every page), and
it ships **its own `@media print` hide** rather than joining the `nav,…` print
rule — that rule lives in `quotation.py`'s `VIEW_DOC_STYLES`, and a page that
does not happen to load that sheet must still not print app chrome.

Colours come from `branding.CSS_TOKENS` as CSS custom properties
(`--brand` red `#D5121A`, `--navy` `#2A086E`, `--saffron`); chart colours come
from `branding.CHART_TOKENS`, which is injected by `DASH_STYLES` only.
Re-theming is a one-file change in `branding.py`.

Money on this page uses **`inr()`** (Indian grouping) and **`compact()`**
(`1.32 Cr` / `13.15 L`), both defined here. They are separate from
`quotation._inr()` on purpose: that one belongs to the printed document, and
`quotation.py` imports *this* module, so it could not be shared the other way.

To add a module card: copy an `<a class="card">` block into `section.mods`, add
an entry to `ICONS`, `url_for("<bp>.<view>")`. The strip is `auto-fit`.

---

### `/product` — Catalogue · [product.py](product.py)

| Route | View |
|---|---|
| `GET /product/` | `list_products` |
| `GET /product/view/<id>` | `view_product` — recursive BOM tree |
| `GET,POST /product/add` | `add_product` |
| `GET /product/delete/<id>` | `delete_product` |

**Seeding.** `ensure_demo_products()` runs at the top of every product route
(and from `quotation.create`). It writes 12 fixed-UUID fire-pump-room items and
flips `STORE["_seeded"]`. Prices are **placeholders, not Samruddhi's rates.**

**List page.** Table with type badge and child count. Assembly rows get a
"View" button. Flash messages arrive as `?msg=&type=success|error`.

**View page.** `_render_tree(product_id, qty, depth, visited)` walks the BOM
recursively, multiplying `qty` down each level. It guards against cycles
(`visited` frozenset) and missing children. Indent classes are driven by depth.
This is where "what's actually inside this assembly" is answered.

**Add page.** Fields: name, part_no, **hsn**, unit (dropdown), base_price,
description, type. Choosing **Assembly** reveals a vanilla-JS child editor
(repeating `child_product_id` / `child_qty` rows).

**HSN/SAC is optional here and mandatory three documents downstream.** That
asymmetry is deliberate — blocking the catalogue would strand anyone holding a
legacy row, because there is no edit route to fix one (below). Instead the list
page, the detail page and every printed sheet show a blank code as the amber
`B.field()` chip, so the gap is visible everywhere it matters and invisible
nowhere.

Validation, in order: required fields → valid type → price ≥ 0 → for each child:
exists, not duplicated, qty is an int ≥ 1, and `can_add_child()` passes.

**Integrity — the two guards you must not remove:**

- `can_add_child(parent, child)` — DFS from `child` through the graph. If
  `parent` is reachable, the edge would create a cycle. Also rejects
  self-reference.
- `can_delete_product(id)` — refuses to delete anything used as a child in any
  assembly, and names the blocking assembly.

**Missing:** there is **no edit route**. Fixing a typo means delete + re-add,
which `can_delete_product` may block. This is the most-requested obvious gap.

---

### `/quotation` — Quotations · [quotation.py](quotation.py)

| Route | View |
|---|---|
| `GET /quotation/` | `list_quotations` — register + pipeline |
| `GET,POST /quotation/create` | `create_quotation` |
| `POST /quotation/<id>/update` | `update_quotation` — pipeline fields only |
| `GET /quotation/view/<id>` | `view_quotation` — the printed document |

#### Register (`/quotation/`)

Four summary tiles (Open Pipeline / PO Expected / Won / Lost, with win-rate and
recorded PO value), then a filter bar, then the table. **All filtering and
aggregation logic is in `pipeline.py`** — `P.summarize()` and
`P.filter_quotations(quotations, request.args)`. Query params `view`, `stage`,
`q` are combinable; `q` searches ref / account / to / PO / buyer ref.

#### Create (`/quotation/create`) — the largest page in the app

A long CRM-style form in sections: quotation meta → lead/ownership → Bill To →
Ship To → commercial terms → tax → product picker.

**Address picker.** `address.picker_options()` renders a `<select>` grouped by
address type; `address.picker_payload()` embeds the whole book as JSON. The JS
`applyAddr(kind, sel)` fills `bill_*` / `ship_*` fields client-side with no
round trip. It collapses `line1 + line2 + landmark` into the one address
textarea, and picking a *shipping* address auto-unticks "same as billing".

**Product picker (the part to understand before editing).** A vanilla-JS model
in a `SEL` array, rendered by `render()` / `renderRoot()` / `renderComp()`.
Adding an assembly pulls in its resolved children from the embedded catalog
JSON (`_product_catalog_json()`). Per row the user can override **qty**,
**price**, and a **show-price** toggle. On submit, `saveJSON()` serialises `SEL`
into the hidden `<input name="selections_json">`.

**On POST:**

1. Read ~40 form fields. `sgst_rate` is **forced equal to `cgst_rate`**.
2. Validate: `account_name` required → `selections_json` parses → at least one
   product → every `pid` still exists in the catalogue.
3. `_process_selections()` flattens `SEL` into `line_items` (depth 0 roots,
   depth 1 components). **`show_price` false ⇒ `price` and `total` become 0.0
   but the row still prints.** That is how "included, no separate charge" lines
   are produced.
4. `subtotal` = sum of all `total`s; `_tax_lines()` computes CGST+SGST / IGST /
   VAT / exempt; `grand_total = subtotal + tax`. `total_qty` counts depth-0 only.
5. Build the `to` address block, assign uuid + `ref`, write to STORE.
6. `P.ensure_fields()` then `P.log_event(q, "Quotation created.")`.
7. Redirect to the view page.

Validation failure re-renders the form with an alert. Note it re-renders from
`request.form`, so the product picker restores from `selections_json`.

#### View (`/quotation/view/<id>`)

Two layers on one page:

- **Deal panel** (screen only, hidden by the `@media print` rule in
  `VIEW_DOC_STYLES`): stage dropdown, PO number/date/value, lost reason,
  quick-action buttons, PO-vs-quoted variance, and the reverse-chronological
  stage history. Posts to `/quotation/<id>/update`. Quick actions are
  **sibling forms**, never nested — nested `<form>` is invalid HTML and
  browsers silently drop the inner one.
- **The document**: letterhead from `branding.py`, To / Ship To block, two
  columns of header meta, the line-items table, tax breakdown, closing total,
  `_amount_in_words()` in the Indian crore/lakh system, and the T&C block from
  `_build_tnc()`.

##### The printed document — `VIEW_DOC_STYLES`

There is **no PDF library.** "Export PDF" is the browser's own *Print → Save as
PDF* of this page, driven by `window.print()`. Everything about the sheet
follows from that. It is modelled on a real trade quotation and holds to four
rules, restated at the top of the stylesheet:

1. **One typeface** — Arial. Money columns use `tabular-nums`, not a second
   monospaced family.
2. **Five type sizes** — `--fs-xs … --fs-xl`. Nothing in between.
3. **Three border weights** — `--rule-box` (heavy frame), `--rule` (cell grid),
   `--rule-hair` (soft separator).
4. **Emphasis is weight and rule, never fill.** The grey table head is the one
   background that carries meaning, and print forces it through with
   `print-color-adjust:exact`; with backgrounds off nothing else changes.

Layout is in **mm**, not rem — the output is A4, and rem is a 16px screen unit
with no relationship to a pt-sized page.

Three things here are load-bearing and easy to break:

- **`.page-frame`** is an outer `<table>` whose `<thead>`/`<tfoot>` hold the
  letterhead and foot strip. `display:table-header-group` is the only mechanism
  a browser gives us to repeat a band on every printed page (`position:fixed`
  does not survive pagination in Chrome). Because it is a real `<table>`, the
  app's bare `table {}` / `thead {}` rules land on it and are inherited by the
  whole document — it explicitly resets `font-size` and `background`.
- **Every property the document cares about is declared, not inherited.**
  `BASE_STYLES`, `PRODUCT_STYLES` and `QUOTATION_STYLES` all ship bare `th`,
  `td`, `table` and `li` rules for the on-screen app and load either side of
  this sheet. A bare `th` beats nothing, so `.q-table th` restates
  `text-transform`, `letter-spacing`, `color`, `font-family` and `font-size`.
  Omitting one is how the column heads silently come out uppercase and grey.
- **The responsive breakpoint is scoped `@media screen and (max-width:760px)`.**
  A4 at 96dpi is ~794px and the printable box is narrower, so an *unscoped*
  max-width breakpoint fires **on paper** and prints the phone layout.

Money on the document goes through **`_inr()`**, which groups in the Indian
system (`13,15,000.00`, not `1,315,000.00`) and emits **no currency symbol** —
the document says INR once, in the amount-in-words line, as the trade does it.
A row priced `0.00` is the "included, no separate charge" convention
(`show_price` off) and prints as `0.00` rather than blank.

Blank header fields print **blank**, never as an em-dash. Deal-desk fields
(sales stage, lead type) are deliberately **not** on the document — they are
internal pipeline data. They stay on the deal panel.

`_build_tnc(q)` composes terms from the saved fields (delivery, tax, payment,
transport, validity) and then appends ~12 **standing clauses** — warranty,
commissioning, short-supply window, force majeure, cheque-return debit note.
⚠ These are generic fire-contractor terms and have **not** been checked against
Samruddhi's actual commercial policy.

**Missing:** there is **no edit or delete route for a quotation.** By design for
the document body (an issued quotation should not have its numbers silently
rewritten) — but there is also no revision/amend flow, despite an `amend_no`
field existing on the record.

**Links out to the proforma invoice.** The view page carries a *Raise Proforma*
button (`/proforma/from/<id>`) and the deal panel lists the PIs already raised
against that quotation as `.pi-chip` links. Both are built from
`STORE["proformas"]` read directly plus `url_for` — `quotation.py` must **not**
import `proforma.py` (§2). `.pi-block` / `.pi-strip` / `.pi-chip` live in
`QUOTATION_STYLES`, not in `PROFORMA_STYLES`, because both modules render them.

**Links across to the buy side.** A *Raise PO* button
(`/purchase/create?quotation_id=<id>`) and, once any PO names this job, a
**job-costing block** on the deal panel: quoted against committed, with the
gross margin and a `.po-chip` per order. Same one-way trick — `STORE["purchases"]`
is read directly, never imported (`purchase.py` imports *this* module). The
`.jc-*` / `.po-chip` classes live in `QUOTATION_STYLES` for the same reason the
PI ones do.

This block is the **only** place the two pipelines touch on screen, and it
touches at the *job*, not at a document. It is material cost only — no labour,
no overhead — and it says so under the figures.

---

### `/proforma` — Proforma Invoices · [proforma.py](proforma.py)

| Route | View |
|---|---|
| `GET /proforma/` | `list_proformas` — register |
| `GET,POST /proforma/from/<qid>` | `create_proforma` — convert a quotation |
| `GET /proforma/view/<id>` | `view_proforma` — the printed document |

**A proforma invoice is a different instrument from the quotation it comes out
of**, which is why it is a separate record and not a render mode. A quotation
is an *offer to sell*; a PI is a *request for money* — it carries its own
number and date, the customer's accounts department files it against a payment,
and it can be raised more than once per deal (advance, balance, part supply).

There is **no blank-PI form**. A PI can only be created from a quotation.

#### Convert (`/proforma/from/<qid>`)

Line items, prices, taxes and addresses are **copied verbatim and not editable
here** — the PI states what was quoted. The form collects only what belongs to
the invoice: its date, the customer's PO reference, how much of the value is
being requested now, and the terms that apply to this payment. The frozen items
are shown read-only underneath so the user sees exactly what they are issuing.

**The terms fields are the same widgets as the quotation form**, not free text:
`payment_terms`, `delivery_terms`, `dispatch_through` and `incoterms` are
dropdowns built from `quotation._PAY_TERMS` / `_DEL_TERMS` / `_DISPATCH` /
`_INCOTERMS` through the shared `_sel_opts()`; `delivery_date` is a date picker
and `validity_days` a number, matching the quotation exactly. **Import those
lists, never re-declare them** — a term one form offers and the other does not
is how the two documents start contradicting each other.

They go through **`_sel_keep()`**, not `_sel_opts()` directly. `_sel_opts` marks
an option selected only on an exact match, so a stored value absent from the
list renders as "nothing selected" and the browser then posts the *first*
option — quietly rewriting a term the customer already saw on the quotation.
`_sel_keep` prepends an unrecognised value and keeps it selected. It matters
here and not on the create form because these values arrive from a saved record
rather than being typed fresh.

##### The second PI is the dangerous one

One quotation can carry several PIs, so the form reads the running position
before it renders anything: `_invoiced_against(qid)` returns
`(total, [refs])` over the PIs already raised, and `_remaining_pct()` turns the
uninvoiced part into a percentage. Three behaviours follow, and they exist
because the arithmetic used to be left entirely to the user:

- **The advance field defaults to what is still uninvoiced, not to 100.**
  `DEFAULT_ADVANCE_PCT` is the default for the *first* PI only. On a
  ₹10,00,000 order already invoiced 30%, the form opens at `70`, and 70 is
  prepended to the `ADVANCE_PRESETS` datalist. **Fully invoiced ⇒ the field
  opens blank**, so a further PI has to be typed deliberately.
- **A `.pi-ledger` states the arithmetic** under the existing `.pi-chip`s —
  quoted value, less already invoiced, still uninvoiced — rather than listing
  the earlier PIs and leaving the user to add them up.
- **Over-invoicing is confirmed, never blocked.** If `prior + due` exceeds
  `grand_total` by more than `OVER_INVOICE_TOLERANCE`, the POST is rejected and
  re-renders with an `.over-confirm` tick box naming the overage and the PIs
  that caused it. Ticking it and resubmitting writes the record. Exceeding the
  quoted value is occasionally right (scope grew, prices moved) and usually a
  slip, so it costs one deliberate act rather than a refusal.

Validation, in order: quotation exists → date present → `advance_pct` parses →
`0 < pct <= 100` → validity is digits → over-invoicing is confirmed. A rejected
POST re-renders with the user's own input (`_v()` prefers `request.form`, then
the quotation's value, then the module default), and nothing is written to
STORE.

On success it writes the record, calls `P.log_event()` on the **quotation** —
raising a PI is a real event in the deal's life and belongs on its audit trail,
though it deliberately does not change the sales stage — and redirects to the
document. The log line carries the **running** position ("Invoiced to date
₹10,00,000 of ₹10,00,000 — fully invoiced."), not just this invoice's figure,
which on its own cannot tell you whether the deal is now covered or billed
twice.

#### The document (`/proforma/view/<id>`)

The same A4 sheet as the quotation: `VIEW_DOC_STYLES` supplies the frame, the
repeating letterhead band, the items table and every print rule, and the money
goes through the same `_inr()`. `PROFORMA_STYLES` layers **after** it, scoped
inside `.quotation-doc`, and introduces no new font, type size or border weight
— it only uses the `--fs-*` and `--rule-*` already defined there. Keep it that
way; that restraint is the reason the two documents look like they came from
the same office.

What a PI has to say that a quotation does not:

- **`.doc-sub`** — "This is not a Tax Invoice", directly under the title inside
  the frame. This is the single most important sentence on the page (it is what
  stops the document being mistaken for a tax invoice), so it prints in the
  frame rather than being buried at clause 1 of the terms.
- **`.pay-box`** — Total value → *(less already invoiced)* → **Amount Payable
  Now** → balance, then the payable-now figure in words. It **breaks the figure
  down only when there is arithmetic to show**: a part payment (`advance_pct <
  100`) or earlier PIs against the same order (`prior_invoiced > 0`). A sole PI
  for the full value gets the compact form — the closing row of the table
  already says that figure, and printing it twice invites the reader to hunt
  for a difference. The payable-now figure carries the heavy rule and the
  `--fs-md` step — the same emphasis the closing total gets, and no more.

  With `prior_invoiced > 0` the head row reads **Total Order Value**, not
  "Total Invoice Value" — `grand_total` is then the value of the whole order
  rather than of this demand — and a `Less: already invoiced on PI-0001` row
  names the earlier PIs, which is what lets the customer's AP team reconcile
  the set. Both figures come off the record, never recomputed (§3.4).

  A **negative** balance (a confirmed over-invoice) prints **no balance row at
  all**: "0.00" would be false comfort and a negative is not a figure anyone
  can act on, so the totals above carry the story.
- **`.bank-box`** — the remittance account, from `branding.BANK_*` (§6). Blank
  fields render as amber `todo-chip`s exactly like the statutory block, so an
  incomplete PI cannot go out looking finished.
- **`_build_pi_terms()`** — PI-specific clauses, deliberately **not**
  `quotation._build_tnc()`. That set is written for an offer (validity, scope,
  warranty, commissioning); this one carries what makes the document readable
  as a payment instrument: not-a-tax-invoice, when the tax invoice will follow,
  that the quotation's terms still govern the supply, retention of title,
  delivery counted from *credit of the advance*, and bank charges.
  ⚠ Generic trade terms, **not checked against Samruddhi's actual policy** —
  same caveat as the quotation's standing clauses.

Unlike `quotation.py`, this module **escapes user input** (`P.esc`) everywhere
it interpolates, including inside `_build_pi_terms()`. §7.7 is the gap, not the
pattern to copy.

#### Numbering

`_next_ref()` scans existing refs and takes **max + 1**, not `len() + 1`.
`len()+1` (what `quotation._next_ref()` still does — §7.5) re-issues a number
that has already been on a customer's document as soon as one record is
removed, and a duplicated *invoice* number is materially worse than a
duplicated quotation number: it is the key the payment is filed against. Still
not year-scoped — `invoice._next_ref()` now shows what that looks like
(`SF/TI/26-27/0001`), and porting it here is a small job. It was done there
first because for a tax invoice FY-scoping is statutory, not a nicety.

#### Links out to the tax invoice

The view page carries a *Raise Tax Invoice* button (`/invoice/from/<id>`) and
lists the invoices already raised against that PI as `.ti-chip` links — the
button relabels itself *Raise Another Tax Invoice* once one exists, because a
part supply is legitimately invoiced in lots. Both are built from
`STORE["invoices"]` read directly plus `url_for`; `proforma.py` must **not**
import `invoice.py` (§2). `.ti-chip` / `.ti-strip` live in `PROFORMA_STYLES`
for the same reason `.pi-chip` lives in `QUOTATION_STYLES`.

---

### `/invoice` — Tax Invoices · [invoice.py](invoice.py)

| Route | View |
|---|---|
| `GET /invoice/` | `list_invoices` — register |
| `GET,POST /invoice/from/<pid>` | `create_invoice` — convert a proforma |
| `GET /invoice/view/<id>` | `view_invoice` — the printed Rule 46 document |

**A tax invoice is the only document in this app with statutory force.** It
creates the GST liability and it is what the customer claims input tax credit
against, so most of its face is dictated by **Rule 46 of the CGST Rules, 2017**
rather than by taste. There is **no blank-invoice form** — it can only be
created from a proforma.

#### Convert (`/invoice/from/<pid>`)

Line items, prices and taxes are **copied verbatim and not editable here**. What
is collected is only what the *supply* knows and the PI could not: when it
happened, where it went, how the goods moved, and how much has already been
received.

**Place of supply** is the field that carries the most weight. It is required,
it is validated against `GST_STATE_CODES`, and it decides IGST (inter-State)
against CGST + SGST (intra-State). It defaults to the ship-to State, then the
source quotation's `bill_state` — *on the form only*. Once posted the answer is
stored on the invoice, so the printed document never depends on the quotation
still existing. `_POS_STATES` deliberately drops the quotation list's `"Other"`:
a foreign supply is an export, which is a different document (LUT/bond, no
IGST) that this app does not issue.

Terms fields reuse the quotation's vocabularies through `_sel_keep()` — the
same rule and the same reason as the PI form (§ above). **Import those lists,
never re-declare them.**

Validation, in order: proforma exists → date present → place of supply present
→ it is a real GST State → `advance_received` parses → it is not more than the
invoice value. A rejected POST re-renders with the user's own input and nothing
is written to STORE.

##### Two warnings, and why neither of them blocks

Both render as an amber `.gst-warn` panel. Amber, not red: nothing is broken,
but nothing here may go out unread.

1. **Missing HSN** (`_missing_hsn()`) names the exact products. It does not
   block, because there is no product edit route (§7.2) — a user holding a
   legacy catalogue row could not clear the block even if they wanted to.
2. **Tax head vs place of supply** (`_tax_warning()`) fires when an inter-State
   supply carries CGST+SGST or an intra-State one carries IGST. It compares
   against `_supplier_state()`, read from the **first two digits of
   `COMPANY_GSTIN`** rather than stored separately — the GSTIN already carries
   the State by construction, and two fields that must agree are two fields
   that can disagree. Blank or specimen GSTIN ⇒ the check stays quiet.

   **It warns and does not correct.** Silently switching the head would move
   the customer's total after they had already agreed a figure. That is a
   commercial decision, not a rounding fix.

#### The document (`/invoice/view/<id>`)

The same A4 sheet again: `VIEW_DOC_STYLES` supplies the frame, the repeating
letterhead, the items table and every print rule; `INVOICE_STYLES` layers after
`PROFORMA_STYLES`, scoped inside `.quotation-doc`, and introduces **no new
font, type size or border weight**. Same restraint, same reason.

What a tax invoice must say that neither of the others does:

- **`.copy-mark`** — goods move in triplicate (Rule 48): *Original for
  Recipient / Duplicate for Transporter / Triplicate for Supplier*. There is no
  PDF library here, so the caption is a render parameter:
  **`?copy=original|duplicate|triplicate|all`**, defaulting to `original`. The
  screen carries a `.copy-switch` segmented control; `?copy=all` emits all three
  sheets with `page-break-before:always` between them, so the full set comes
  out of one Ctrl+P. `page-break-before`, not `break-before` — Chrome's print
  path still honours the legacy property most reliably.
- **`.gst-strip`** — place of supply, its State code, and the reverse-charge
  declaration, in a band under the header grid. Rule 46(m) and 46(n) want these
  on the *face* of the invoice, and they are the first thing the customer's
  accounts team reads, so they are not mixed into the meta columns.
  **The reverse-charge line prints either way** — "No" is a required
  declaration, not an omission.
- **Per-line HSN via `_hsn_cell()`** → `B.field()`, so a blank prints as the
  amber chip and, under the `@media print` override in `QUOTATION_STYLES`, as
  bracketed italics rather than a yellow pill on a customer's document.
- **`.set-box`** — Total invoice value → less advance received → **Net Amount
  Payable**, then that figure in words. **Only rendered when an advance was
  actually adjusted**; with nothing received the closing row of the table is
  already the amount due, and printing the same figure twice invites the reader
  to hunt for a difference. Same judgement as the PI's `.pay-box`.
- **`.desp-box`** — vehicle no., LR/docket, e-way bill. Rendered only when at
  least one was captured, for the same reason `_meta()` leaves a blank value
  blank rather than printing an em-dash.
- **`.certify`** — the "particulars given above are true and correct"
  declaration above the signature block.
- **`_build_ti_terms()`** — deliberately neither `quotation._build_tnc()` nor
  `proforma._build_pi_terms()`. Those are written for an offer and for a payment
  request; this set carries what belongs to a completed supply: what it was
  supplied against, the short-supply window, retention of title, interest on
  overdue amounts, and jurisdiction.
  ⚠ Generic trade terms, **not checked against Samruddhi's actual policy** —
  same caveat as the other two.

The closing figure is labelled **"Taxable Value"**, not "Subtotal": on a tax
invoice that figure is the base the tax was computed on, and that is the term
both the customer's accounts team and the GST return use for it.

Like `proforma.py` and unlike `quotation.py`, this module **escapes user input**
(`P.esc`) everywhere it interpolates. §7.7 is the gap, not the pattern.

#### Numbering

`_next_ref(date)` is **FY-scoped and max+1 within that FY** — `SF/TI/26-27/0001`,
exactly 16 characters, which is Rule 46(b)'s cap. Three things it does
deliberately:

- **The FY comes from the invoice date, not from today** (`_fy_of()`), so
  back-dating into March files under the closing year and 1 April opens the new
  series. A malformed date falls back to today rather than raising.
- **Max+1 within the year**, so deleting a record never re-issues a number that
  has already reached a customer's GSTR-2B.
- **If `COMPANY_SHORT` is long enough to push the ref past 16 characters, the
  prefix is dropped** rather than issuing an over-length number — a number the
  portal will reject is worse than an unbranded one.

#### Business rules — module-level constants, not buried in branches

⚠ These are **`proforma.py`'s** constants; the block sits here only because the
`/invoice` section was inserted above it. Move it back under `/proforma` next
time this file is edited.

`DEFAULT_ADVANCE_PCT` (100 — asking for less must be deliberate). This is the
default for the **first** PI on a quotation only: once earlier PIs exist the
form opens at whatever is still uninvoiced, because 100 is the safe default for
the first invoice and the dangerous one for the second.
`OVER_INVOICE_TOLERANCE` (₹1 of rounding dust forgiven before a PI set counts
as over-invoiced — three PIs at 33.34% come to 100.02% and are not a mistake).
`DEFAULT_PI_VALIDITY` (15 days, shorter than a quotation's on purpose),
`ADVANCE_PRESETS`, `_REF_PREFIX`.

---

### `/purchase` — Purchase Orders · [purchase.py](purchase.py) · **BUY SIDE**

| Route | View |
|---|---|
| `GET /purchase/` | `list_purchases` — register, filterable by status |
| `GET,POST /purchase/create` | `create_purchase` — raise a PO on a vendor |
| `POST /purchase/<id>/update` | `update_purchase` — status only |
| `GET /purchase/view/<id>` | `view_purchase` — the printed purchase order |

**Read §1 "There are two pipelines" before editing this file.** This is the
only module where money goes *out*, and it links to no sell-side document.

#### The inversion you must hold in your head

On every other printed document **we are the seller**. Here **we are the
buyer**, and three things flip:

| | quotation / PI / TI | purchase order |
|---|---|---|
| letterhead | us | us |
| the **"To"** block | the CUSTOMER | the **VENDOR** |
| delivery block | where we ship **to them** | where they deliver **to us** |
| the tax | **output** tax we collect | **input** tax we pay |

Getting the "To" block wrong means sending our own address to a supplier as the
party to invoice. `_vendor_block()` and `_delivery_block()` are named for the
**roles**, not for their positions on the page, to make that hard to slip.

#### Create (`/purchase/create`)

Entered from scratch. The line editor is the **repeating-row pattern from
`product.py`'s BOM child editor**, not the quotation's `SEL` JS model — a PO is
a handful of flat rows and does not need a client-side model. Rows post as
parallel `line_product_id` / `line_qty` / `line_rate` lists and are read by
`_parse_lines()`, which **skips blank rows silently** (the editor opens with
three, and an untouched one is not a mistake).

The catalogue price is **suggested, never imposed**: `fillRate()` fills the rate
box only when it is empty, because `base_price` is what we *sell* at and what a
vendor charges us is a different number.

Widgets are shared, not re-declared: the vendor picker is
`address.picker_options(only_types=("vendor",))` and the terms are the same
`_PAY_TERMS` / `_DEL_TERMS` / `_DISPATCH` / `_INCOTERMS` the sell-side forms
offer — "By Road Transport" must mean the same thing whichever way the goods
move.

Validation, in order: date → vendor chosen → vendor still exists → status valid
→ job (if given) still exists → lines parse, each with qty > 0 and rate ≥ 0 →
at least one line. A rejected POST re-renders with the user's rows intact and
writes nothing.

`?quotation_id=<id>` pre-selects the job, which is how the quotation's **Raise
PO** button works. It is a query param rather than a path segment on purpose: a
PO is *not derived* from a quotation the way a PI is, and it can be raised with
no job at all.

#### The lifecycle — this is the "different procedure"

A sell-side document is issued once and then stands. A PO is a **commitment
that has to be chased**, which is the substantive reason purchasing is its own
pipeline rather than a fourth link in the chain.

```
Draft → Issued → Acknowledged → Partially Received → Received
                                                   ↘ Cancelled
```

`PO_STATUSES` is a module-level constant — edit it and the create dropdown, the
register's filter tabs, the badges and the panel all regenerate.
`CLOSED_STATUSES` (Received, Cancelled) is the buy-side equivalent of
`pipeline.OPEN_STAGES`; `CHASE_STATUSES` drives the "issued but never
acknowledged" tile, which is how a delivery date quietly slips.

`update_purchase()` changes **status only**. The commercial content of an
issued PO is not editable — a vendor has been told a price and a quantity, and
changing them behind the document is how a dispute starts. An amendment means a
fresh PO.

#### Job costing — `job_cost(quotation_id)`

The whole reason the optional link exists. Public, because `quotation.py`
renders it on the deal panel:

```
Quoted  ₹10,03,000   Committed  ₹3,10,340   Gross Margin  ₹6,92,660  (69.1%)
```

- **Cancelled POs are excluded from committed spend** — a withdrawn commitment
  is not a cost — but are still counted in `count`, so the panel never silently
  loses a document somebody raised.
- The margin percentage is **guarded against a zero divisor**: a quotation can
  legitimately total zero (everything marked "included, no separate charge"),
  and a `ZeroDivisionError` on the deal panel is a 500 on a page opened daily.
- It is **material only** — no labour, no overhead — and the panel says so.

#### The document

The same A4 sheet (`VIEW_DOC_STYLES`), so everything leaving this office looks
like it came from the same place. `PURCHASE_STYLES` layers after it and
introduces no new font, type size or border weight — same restraint as
`PROFORMA_STYLES` and `INVOICE_STYLES`. It deliberately does **not** load either
of those sheets: borrowing a sell-side stylesheet is how the separation would
quietly rot.

What a PO says that no sell-side document does:

- **`.doc-sub-po`** — "Order placed on supplier", so a vendor cannot mistake it
  for our quotation.
- **`.po-status-strip`** — status, required-by date, and "This order is placed
  by us as buyer" in plain words.
- **Instructions to Supplier** — quote our PO number on the invoice; **send us a
  Rule 46 compliant tax invoice** (we cannot claim input tax credit against a
  deficient one, and lost credit is recovered from their payment); deliver to
  the stated address by the stated date; goods accepted subject to inspection;
  prices firm; no amendment on the invoice alone.
  ⚠ Generic buyer's terms, **not checked against Samruddhi's actual purchasing
  policy** — same caveat as the other three documents.

#### Numbering

`SF/PO/26-27/0001` — FY-scoped and max+1 within the year, sharing
`pipeline.fy_of` / `fy_ref` with the tax invoice. **No 16-character cap**: that
is Rule 46's limit on what we issue *as a supplier*, and here we are the
customer. A buyer's series still has to be unique and non-repeating, because it
is the key the vendor quotes on their invoice and the key we match it against.

---

### `/spec` — Specification Library · [spec.py](spec.py)

| Route | View |
|---|---|
| `GET /spec/` | `list_specs` — register, filtered by category |
| `GET /spec/view/<id>` | `view_spec` — clause + variant table |
| `GET,POST /spec/add` | `add_spec` |
| `GET,POST /spec/edit/<id>` | `edit_spec` |
| `GET /spec/delete/<id>` | `delete_spec` |

**Read the Specification entry in §3 before editing this file**, and do not
confuse it with `product.py` — the two describe different things and both are
live.

**Edit exists from day one.** §7.2 calls `product.py`'s missing edit route the
highest-value gap in the repo; a library of 56 clauses, several of them 1300
characters, cannot be maintained by delete-and-re-add. `add` and `edit` share
`_render_form()` and `_validate()` so they cannot drift, and `_validate()`
**always returns data** — a rejected form re-renders with the user's clause
intact. That contract comes from `address._validate()`, the one module in this
repo that already did edit properly.

**Delete has no dependency guard, deliberately.** `product.can_delete_product()`
blocks removal of anything used as a child in an assembly, because a BOM holds a
live `product_id`. Nothing equivalent exists here: a BOQ line carries **no
`spec_id`**, because `spec_text`, the rates, the unit and the tax codes are all
*copied* onto the line when it is written. A spec therefore has no dependents by
construction and deleting one cannot reach a BOQ, issued or draft. The
trade-off, stated plainly: there is no traceability from a BOQ line back to the
library entry it came from. Adding one would mean a field on a contracted shape
that becomes a lie the moment the line is edited away from the spec.

**The variant editor clones a server-rendered `<template>`**, using
`purchase.py`'s precedent, rather than building a row in JavaScript. There are
two ways to get an "add row" button wrong and both are real: building the row
in JS duplicates the markup somewhere it can silently drift (`product.py`'s BOM
editor does this and currently matches — nothing guarantees it still will), and
assigning the server's row HTML into a fresh wrapper `div` nests `.var-row`
inside `.var-row`, so the inner grid gets one column's width and the inputs
collapse. Cloning a template has neither failure mode.

**The seeded rates are one project's figures, not a price list.** 56 clauses
seed from `demo_data.SPECS` via `ensure_demo_specs()`, generated from the
client's Sify Bangalore workbook. `REFERENCE_NOTE` says so on the register, the
view page and both forms. There is deliberately **no per-row provenance
field** — library rates are defaults that get overridden per project anyway, so
it has not earned its place. It becomes a real question when the client runs
several projects on different rate bases.

⚠ **The HSN and SAC codes are placeholders**, assigned by category. The source
workbook carries none. Same caveat as `product._seed()`'s twelve rows, and it
matters more here because a BOQ line carries two of them.

---

### `/boq` — Bills of Quantities · [boq.py](boq.py)

| Route | View |
|---|---|
| `GET /boq/` | `list_boqs` — register |
| `GET,POST /boq/create` | `create_boq` |
| `GET /boq/view/<id>` | `view_boq` — the printed schedule |

**Read §2b before editing this file.** A BOQ is the head of its own chain and
is not a quotation with more columns.

#### Create (`/boq/create`)

Sections first, then lines. **Areas are declared on the section**, as a
comma-separated list, because one section may break its quantities down by
floor while the next does not break them down at all.

The line editor is a **browser-side model serialised into one hidden field**
(`boq_json`) on submit — the quotation's `selections_json` pattern, not
`purchase.py`'s parallel form-field lists. It has to be: the area quantity
boxes on a line depend on which section the line is in, so the field set is not
fixed. Changing a line's section re-renders its area boxes and drops any
quantity keyed to an area the new section does not declare — visibly, rather
than silently on save.

`_BOQ_JS` is a **plain string, not an f-string**, so its braces are written
once (the `DASH_STYLES` precedent). It still has to avoid `{{` and `{%`,
because `render_template_string` runs Jinja over the output.

Two rate behaviours worth keeping:

- **With an area breakdown, the total IS the breakdown** — `total_qty` is
  derived and shown read-only. Two independently typed figures that must agree
  are two figures that can disagree. A section with no areas takes a typed
  total.
- **The escalated rate is a suggestion, never imposed.** The form offers
  `base × (1 + pct)` beside an empty rate box with a *use* link, and when the
  entered rate differs it says so and keeps what was entered —
  `purchase.fillRate()` makes exactly the same call about a catalogue price.

Validation, in order: JSON parses → date → project name → account name →
sections have unique codes → **line count within `MAX_LINES`** → **payload
within `MAX_JSON_BYTES`** → every line's section exists → item number present → description present → quantities and
rates parse and are non-negative → HSN/SAC shape valid when filled. A rejected
POST re-renders from the posted JSON, so nothing typed is lost and nothing is
written to STORE.

##### The 600-line cap — `MAX_LINES`

A *persistence* limit wearing a validation hat. The whole BOQ is one JSON
document in one MySQL column (§4), so a schedule large enough to be refused by
the server is a record that **can never be written** — and because a failed
sync now retries every request instead of giving up, that record would be
re-offered and re-refused forever, keeping the persistence strip lit and
burning a round trip per request. The cap is what stops it existing.

600 against a real schedule of 97: the client's largest workbook is under 150
lines, and a project needing four times that is two projects. It is a
deliberate limit, not a guess at a technical ceiling.

It is checked **first**, before any per-line rule — validating 5000 rows to
then reject the lot for being 5000 rows is work nobody asked for, and "line 12
needs a description" is the wrong complaint about a schedule 400 lines too
long. It reports **the first line past the limit** as the offender, so the
re-render opens the row where the BOQ stopped being acceptable rather than the
last one added, and it holds to the same contract as every other rule here:
nothing lost, the line named, that line and its section forced open.

##### `MAX_JSON_BYTES` — the cap that actually binds

> **Corrected.** This section previously said 600 lines is ~420 KB and fits
> under `MAX_FORM_MEMORY_SIZE`. That compared the **decoded JSON** against a
> limit which applies to the **URL-encoded body**, and the wire is bigger than
> the payload — `application/x-www-form-urlencoded` percent-escapes every
> quote, brace, comma, colon, space and newline, and JSON is made of those.

Measured expansion:

| shape | JSON | on the wire | ratio |
|---|---|---|---|
| real demo BOQ, 97 lines | 701 B/line | **955 B/line** | 1.36 |
| terse synthetic lines | 455 B/line | 685 B/line | 1.51 |

At 955 encoded bytes a line a **real**-shaped BOQ reaches 500,000 bytes at
~523 lines — *below* `MAX_LINES`. A 524-line schedule would therefore 413
before any validation ran, losing the editor, which is the exact failure the
cap exists to prevent.

So `_clean_lines()` also takes the byte length of the posted `boq_json` and
rejects past **`MAX_JSON_BYTES = 300,000`**. 300,000 × the worst observed 1.51
expansion is 453,000 on the wire, leaving ~47 KB for the twenty other form
fields (`notes` is the only one that can be large), so the check always fires
first. Its `err_idx` is **-1** and its message blames the schedule rather than a
line — no single row is at fault, and forcing one open would point the user at
a row that is not the problem.

**The two caps bind on different schedules and both are needed:** `MAX_LINES`
catches many terse lines, `MAX_JSON_BYTES` catches fewer verbose ones. For the
client's real data shape the byte cap binds first, at ~428 lines. The line cap
is reported first when both are breached, because "remove 40 lines" is
actionable and "too large" is the fallback.

⚠ **Not a security boundary.** A hostile payload of nothing but escaped quotes
expands 3× and would still 413. `MAX_FORM_MEMORY_SIZE` stays at 500,000 and
remains the real limit, with the 413 handler (§7.6) behind it. This is a
*usability* boundary: it keeps an honest BOQ from ever hitting that wall.
`test_no_realistic_boq_shape_can_reach_a_413_through_the_form` asserts the
property against every line shape the app has seen, and names the shape that
broke it if a future one expands worse.

#### The spec picker, and inserting a whole size family

The per-line picker reads `/spec`, **not the product catalogue** —
`product.base_price` is what we sell a unit of stock for and is not a BOQ
supply rate. Choosing a **spec** fills the description, HSN, SAC and both GST
rates; choosing a **variant** fills the unit and *suggests* both base rates.
The unit comes from the variant rather than the spec because that is where it
lives — for an unsized spec, where no size remains to be chosen, it arrives
with the spec.

##### Navigating 97 lines

A BOQ is long, and rendered as stacked full-height panels the form is less
usable than the spreadsheet it replaces. So the editor shows a **one-line
summary** per line — item no · description · qty · supply rate · install rate —
and opens the full panel only for the line being worked on.

**The summary is the deliverable.** Collapsing is how it becomes readable.

- **Sections** collapse to a bar carrying the line count and that section's own
  supply and installation totals.
- **A closed header folds its family**: item 24 shut takes 24.a–24.i with it,
  because that is how the schedule reads on paper. Its summary says
  `spec · 9 items`.
- **A jump bar** (sticky) offers one button per section plus expand-all and
  collapse-all. Jumping opens the section it lands on.
- **Newly added and newly edited lines stay open**; adding into a collapsed
  section opens that section, because a new line the user cannot see is worse
  than no new line.
- **Bulk insert opens the header only** — ten expanded panels is the problem
  this exists to avoid.
- **Orphan lines get their own band.** A line whose section no longer exists
  was previously invisible while still posting and still counting; it now shows
  under a red bar telling the user to give it a section or remove it.
- **Priced lines with no quantity get an amber band** (`renderZeroQty()`).
  A line carrying a base rate, an escalation and a unit rate but Total Qty 0
  contributes 0.00 to the subtotal; a schedule made only of those shows a full
  set of rates against a grand total of zero with nothing saying why, which
  reads as a broken form. It is a **hint, not an error** — quantities are
  provisional and billed as executed (the printed footer says so), so a line
  awaiting site measurement is correct. **Specification headers are not
  counted**: a header carries the clause and no quantity by design, and
  flagging it would be noise. The band also names the RA consequence, which is
  the part worth knowing at entry time rather than later —
  `ra.approved_by_line()` reads `total_qty`, so a line approved at 0 has
  nothing to claim against and every RA claim on it is refused by the
  over-claim block.
- **Repeated item numbers get an amber band** (`renderDupWarn()`), live as the
  user types. Two lines in the same section sharing an item number will print
  alike and be hard to tell apart on a measurement sheet — worth saying. It
  **warns and never blocks**, and it says so on its face: each line is tracked
  by its own `line_id`, so their claims cannot run together and billing is
  unaffected. The client's own Sify schedule trips it — section A carries item
  17 twice, in *their* source workbook — which is why this reports the
  ambiguity rather than correcting it. Amber, not red, per the severity rule
  above: incomplete but working.

Open/closed state lives on the line (`_open`) and on the section (`_open`),
**never in a map keyed by row index** — that is the class of bug the spec
picker's `PICK` map fell into, where deleting a line made every row below it
show the previous row's state. Absent means closed, so a loaded BOQ opens fully
collapsed and `_demo_form_payload()` says nothing about it.

##### UI state is posted, and the server is what keeps it out of the record

`_open`, `_spec`, `_variant` and `_auto` are all posted inside `boq_json`. That
is deliberate. Stripping them in `saveJSON()` would also throw them away on a
**rejected** POST, and the user would get their input back with every line
slammed shut and the picker's typed/auto memory wiped — the opposite of the
always-return-the-user's-input contract this form is held to.

The record stays clean **by construction on the server**: `_clean_lines()` and
`_clean_sections()` build a fresh dict out of named keys, so an underscore key
cannot get in whatever the browser sends. `test_no_ui_state_reaches_the_record`
asserts exactly that, end to end.

**A rejected POST forces the offending line open.** `_clean_lines()` returns
the failing row's index alongside the message, and the re-render opens that
line and its section. Every line is collapsed by default, so a complaint about
line 47 that leaves line 47 shut is worse than no validation.

##### What a pick does to a row — the rule

Every field on a line is in exactly one of three states:

| state | meaning |
|---|---|
| **empty** | nothing in it |
| **auto** | what is in it was put there by the picker |
| **typed** | the user edited it by hand |

**A pick overwrites empty and auto, and never overwrites typed.** From that:

1. Choosing a **spec** fills description, HSN, SAC and both GST rates.
2. Choosing a spec also **resets the variant** — unit and the two base rates
   belonged to a variant of the *previous* spec, so any still marked auto are
   cleared. Anything typed survives.
3. Choosing a **variant** fills unit, both base rates, and sets the description
   to the variant's label.
4. An **unsized** spec applies its single variant immediately; there is no size
   left to choose.
5. Typing in a field marks it typed for good. Later picks leave it alone.
6. `hint()` still says "escalation implies X — rate differs, kept as entered"
   rather than correcting a rate.

⚠ **This was the bug.** The original rule was just "fill an empty box", which
is right for a blank row and wrong for a re-selection: once a row had been
populated, changing the spec did nothing and choosing a variant did nothing, so
a row could sit showing one spec in its picker and another spec's description
and unit. The `_auto` map is what distinguishes a value the picker wrote from
one a human chose.

`_spec`, `_variant` and `_auto` live **on the line**, not in a map keyed by row
index. An index-keyed map desyncs the moment a line is deleted — every row
below inherits the previous row's spec. They are stripped in `saveJSON()`, so a
BOQ line still carries no `spec_id`.

Variant options carry the variant's **index**, not its label: five seeded
labels are multi-line pump specifications, and matching those back through an
HTML attribute is fragile for no benefit.

**"Insert header & variants"** expands a sized spec into the shape the client's
sheet is actually written in — one header row carrying the clause, then one
child per variant, numbered `24`, `24.a`, `24.b`… taking the next whole number
free in that section. An unsized spec inserts a single plain line. Without it,
item 24 is ten rows of typing.

Those fill rules are the one piece of behaviour in this app that only exists in
JavaScript, so [tests/test_picker_js.py](tests/test_picker_js.py) runs the real
`_BOQ_JS` under Node against the real payload. It skips when Node is absent.

⚠ **That file lied once and the reasons are worth knowing**, because they are
how any JS harness lies. It (a) called the handlers directly instead of firing
the rendered `<select onchange=…>`, so the wiring was never under test; (b)
started every case from a fresh blank row, which was the one input where the
broken fill rule still worked; and (c) ran each case in its own process, so no
state carried between actions and an index-keyed desync could not appear. It
now fires the rendered control, runs multi-step sequences in one process, and
asserts on behaviour rather than on source strings. Twelve of its tests fail
against the code it used to pass.

#### Loading the demo into the form — `?demo=1`

`GET /boq/create?demo=1` fills the editor from the seeded record: 3 sections,
97 lines, every rate and area quantity, plus the project and terms fields. A
blue banner says what was loaded and that **nothing has been saved** — a form
that fills itself with 97 lines otherwise reads as a BOQ that now exists.

It reads the seeded *record*, not `demo_data` directly, so what the form loads
is exactly what `/boq/view` shows. The round trip is lossless: posting it back
unchanged reproduces all three section subtotals. There is a test for that,
because "load" and "save" agreeing is the whole value of the feature.

It exists because a 97-line schedule cannot be hand-built to try the form out,
and a form that cannot be exercised cannot be reviewed.

#### The demo BOQ

`ensure_demo_boq()` seeds **one complete Sify Bangalore schedule** — three
sections, 97 lines, `External`+`L0` / `T1` / no areas — built from the seeded
specs by code, along the same path the picker takes. It exists so the system can
be shown working without anybody typing 120 lines first.

Both seed flags (`_spec_seeded`, `_boq_seeded`) are **not persisted**, so
dropping the database and restarting refills them; both records carry fixed
UUIDs, so re-running never duplicates and never overwrites an edit.

The line rates come from the seed table, **not** re-derived from the library
defaults: twelve lines in this schedule deliberately differ from
`base × (1 + escalation)` for a documented commercial reason (a tamper switch
at ₹2000/nos, a larger diameter at the Bangalore site), and re-deriving them
would erase those decisions and break the subtotals.

#### The document (`/boq/view/<id>`)

The same A4 sheet — `VIEW_DOC_STYLES` supplies the frame, the repeating
letterhead and every print rule, money goes through the same `_inr()`, and
`BOQ_STYLES` layers after it introducing no new font, type size or border
weight. It changes exactly one thing about the page:

**⚠ It prints LANDSCAPE.** The fixed columns come to ~167mm before a single
area column or a character of description; A4 portrait gives 192mm. The
alternative was dropping the area breakdown, which is worse — those columns are
the only place `total_qty` is substantiated, and a sheet that cannot be checked
against the workbook it came from is a summary, not a document. `BOQ_STYLES`
overrides `@page` and `.doc-outer` **as layered overrides, never as edits** to
`VIEW_DOC_STYLES`; the quotation, PI, TI and PO sheets are untouched and still
portrait.

**One table per section**, each with its own `colgroup` and column heads,
mirroring the source workbook. A single table whose column count changes
halfway down is not a table.

- A **specification header** spans the numeric columns rather than leaving a
  row of blanks that reads as missing data.
- A **blank area cell** prints blank, not `0` — the item is not on that floor,
  which is a different claim from "none of them here".
- A **`-` base rate** prints as `-`. A **missing rate** prints blank while its
  amount still prints `0.00`, exactly as the client's own sheet renders a
  nil-priced line.
- **Escalation columns are hidden when every line in the BOQ has none**
  (`HIDE_EMPTY_ESCALATION`) — on a sheet already fighting for width, the
  description needs the millimetres more than an empty column does. Same
  judgement as the PI's `.pay-box`.
- **`remark` does not print** (`PRINT_REMARKS`). It holds internal pricing
  notes — "2000/nos extra for Tamper switch" — and the same judgement that
  keeps deal-desk fields off the quotation keeps these off the customer's copy.
  Flip the constant if the client wants them.
- **No tax is computed** (`PRINT_TAX`). The client's own summary says "TAXES
  WILL BE EXTRA" on its face and the liability falls due as the work is billed,
  not when the schedule is agreed. `supply_gst_rate` / `install_gst_rate` are
  captured per line for whatever raises it, not used here.

  > **[Corrected 8 Aug 2026]** The client's actual as-submitted RA bill was obtained and is explicitly headed "TAX INVOICE". **The requirement that the RA bill must act as a tax invoice is now active**, owned by [DOMAIN.md §4](DOMAIN.md), overriding previous design assumptions.
  >
  > *(Superseded history)*: This used to read "the liability falls due on the RA bill, which is the tax invoice". It was then incorrectly changed to assert that an RA bill is a claim document and is deliberately not a tax invoice — no Rule 46 fields, no place of supply, no e-invoicing (`PHASE4_RA_DESIGN.md` §5), under the false premise that the project tax-invoice chain is a separate module later that would carry the liability.

Like `proforma.py` and unlike `quotation.py`, this module **escapes user input**
(`P.esc`) everywhere it interpolates. §7.7 is the gap, not the pattern.

#### Numbering

`SF/BOQ/26-27/0001` — FY-scoped and max+1 within the year, sharing
`pipeline.fy_of` / `fy_ref` with the tax invoice and the purchase order. **No
16-character cap**: that is Rule 46(b)'s limit on a tax invoice number, and a
BOQ is a priced schedule, not a statutory record. It still has to be unique and
non-repeating, because it is the key every RA bill quotes back.

---

### `/ra` — Running Account Bills · [ra.py](ra.py)

| Route | View |
|---|---|
| `GET /ra/` | `list_ras` — RA register listing, grouped/sorted by BOQ |
| `GET,POST /ra/create` | `create_ra` — BOQ picker, then the claim grid |
| `GET /ra/view/<id>` | `view_ra` — a working screen, not the printed sheet |
| `GET,POST /ra/edit/<id>` | `edit_ra` — gated to the latest bill |
| `GET,POST /ra/certify/<id>` | `certify_ra` — certification entry UI, editable on any bill |
| `GET /ra/print/<id>` | `print_ra` — printed RA bill tax invoice document (DOMAIN.md §4) |
| `GET,POST /ra/delete/<id>` | `delete_ra` — GET confirms, POST deletes |

✅ **Step 4 shipped `/ra/print/<id>` (the printed RA bill tax invoice document).**

**Registering this blueprint is what closes the `/boq/view` 500** (§2b).

#### `/ra/print/<id>` reads the RECORD, never the live BOQ

The printed bill is an issued **tax invoice**, so the rule from §3 applies to it
without exception: **every value on the page comes from `bill`.** Item numbers,
descriptions, units, quantities, rates, amounts, HSN/SAC codes, the six
party/project fields, and every total including CGST/SGST/rounding/grand — all
stored, all read, none recomputed and none looked up.

⚠ **It did not, and the failure was invisible.** The document was built as a
loop over `boq["line_items"]`, which let three live reads through: the **item
number** printed the current BOQ's label over the snapshot `/ra/view` correctly
shows; the **row set and row order** followed the current schedule, so a line
dropped from the BOQ vanished from the table while its amount stayed inside the
printed Claim Subtotal — *an invoice whose rows did not add up to its own
total*; and the buyer/project block fell back to the live BOQ whenever the
bill's own copy was blank. The suite was green throughout, because every print
test rendered a bill against a BOQ nobody then touched.

`tests/test_ra_print_immutability.py` is the test that was missing. It issues a
bill, revises the schedule underneath it — rate, quantity, HSN, item number,
description, unit, and outright deletion of a claimed line — and asserts the
rendered page is **byte-identical**. Four of its eight cases fail against the
pre-fix renderer.

**The one thing read from the live BOQ is the specification-header relation**
(`parent_item_no` → the header line), because no claim row carries it. The
header's own paragraph is therefore the single value on the page that still
tracks the schedule, and it is the single thing that disappears if the BOQ
record does. Closing that would mean snapshotting the header text onto the bill
at save — a record-shape change, not made here. Nothing else on the document
depends on the BOQ existing at all.

A spec header prints only when a line **under it** is claimed, and prints **in
full** — `boq.view_boq()` prints the same paragraph in full, and an ellipsis
dropped into the middle of a specification clause on a tax invoice is a
document saying something other than what was agreed.

#### The seller block is read from `/settings`, and the State is derived

The **buyer** half of the party block is the bill's own snapshot (above). The
**seller** half is the live company identity, read through `branding` exactly as
the bank block beneath it is — `B.COMPANY_LEGAL or B.COMPANY_NAME`,
`B.COMPANY_GSTIN`, `B.COMPANY_ADDR`. That is the correct direction for this
half: our own GSTIN is not a fact about the claim, it is who we are today, and a
snapshot of it would go stale the day the registration changes.

⚠ **It carried a hardcoded GSTIN and a hardcoded State until 2026-08-10**, and
printed both on the face of a tax invoice. The GSTIN sat behind an `or`, so it
appeared only once the real identity was missing — the one moment nobody is
checking. There is now **no fallback behind any of the three**: a field blank in
settings prints an em dash, which is the same "a missing statutory detail must
be visible" contract §5 `/settings` already states.

**The State is derived from the GSTIN, never stored beside it** —
`P.gstin_state_label(B.COMPANY_GSTIN)` → `Maharashtra (27)`. Two fields that
must agree are two fields that can disagree; `invoice._supplier_state()` made
the same argument first. `tests/test_ra_seller_identity.py` greps the module and
fails if any State name or any GSTIN-shaped string reappears anywhere in
`ra.py`, including in a comment.

#### The claim grid

- **Every line of the approved BOQ is rendered**, in BOQ order, claim quantity
  defaulting to 0 — never a shortlist. The operator works from a site
  measurement sheet against item numbers, and hiding an exhausted line hides
  the fact that it *is* exhausted, which is the state most likely to be
  mis-claimed. An exhausted line is greyed with its balance called out, not
  removed. Specification headers render as context and carry no inputs.

##### Navigating 97 lines here too — the family fold

Rendered flat, the real Sify schedule is 97 stacked rows of which ten carry
specification paragraphs of 237–1369 characters. So the grid folds, and it is
**boq.py's fold ported over** rather than a second design: the same `is-spec` /
`is-child` class names, the same `.ls-chev` / `.ls-tag` summary furniture, the
same `cursor:pointer; user-select:none` affordance, the same
`spec · N items` count, and the same collapsed-on-arrival default. A closed
header takes its family with it — item 24 shut takes 24.a–24.i — because that
is how the schedule reads on paper. Forty of the ninety-seven rows are children
of one of the ten headers.

**One difference from boq.py, in mechanism only, and it is forced.** boq.py
re-renders its editor from a browser-side model and simply does not emit a
folded child. This grid is *server-rendered*, and every row carries the two
`<input>`s that make up the POST body — so a folded row is **hidden**
(`display:none`), never removed. Folding must not be able to change what saves,
and `tests/test_ra_collapse_js.py` runs the real toggles under Node against the
real page and diffs `ra_json` to prove it does not.

Consequences of that mechanism, all of them deliberate:

- Open/closed state lives on the **header row, keyed by its `line_id`** — never
  in a map keyed by row index. Same lesson as `_open` on a BOQ line, and this
  grid is where an index key would bite hardest: section A carries item 17
  twice.
- `_families()` computes the map **server-side**, for the reason
  `_duplicate_items()` does — on this form the line set is fixed and there is
  no browser-side model to consult.
- A family **opens on arrival when one of its children already carries a
  figure**. That is boq.py's "a rejected POST forces the offending line open"
  contract, and it is also what makes `/ra/edit` show the lines the bill
  actually claimed instead of a wall of shut headers.
- A header with **no** children is not a fold point — no chevron, no click
  target.
- Expand-all / collapse-all sit above the table. boq.py hangs them off its
  sticky jump bar; there are no sections to jump between here.

##### The description column is NOT nowrap

A claim-entry table is read against a **paper measurement sheet**, one row at a
time. `white-space: nowrap` with an ellipsis and a hover `title` fails on a
touch screen and fails again when the two documents are open side by side —
which is the only way this form is ever used. So:

- **Child and standalone lines wrap to two lines** (`.cl-clamp`,
  `-webkit-line-clamp: 2`) and carry their **whole** description in the cell.
  The full text was already on the page in the `title` attribute, so this costs
  nothing on the wire.
- **Only the parent header row is clamped to one line** (`.ls-desc`) — it holds
  a specification paragraph, and a paragraph is not a table row.

The clamp is presentation, top to bottom: every BOQ line still renders, every
quantity still defaults to 0, every input is still in the POST body whatever is
folded, and `clean_claims()` still drops the zero-quantity lines on save.
- **Sparse storage, complete display.** A line claimed at zero is dropped on
  save. It keeps `ra_bills` small, keeps `claimed_by_line()` cheap, and means
  an untouched line never asserts a claim of zero it never made.
- Per line: approved qty, cumulative claimed to date, balance, this bill's
  quantity and rate, amount. The over-claim and rate-divergence styling update
  **on every keystroke**, so the breach is visible while it is being typed.
- **The duplicate-item_no band is here too**, for the same reason it is on the
  BOQ form — the operator sees two rows both labelled 17 and needs telling they
  are separate items, guarded separately. Computed server-side here, because on
  this form the line set is fixed and cannot be edited.
- The **deductions list is rendered and empty**, as designed (§6.3 of the
  design doc).

#### One leg per bill, by construction

The leg is a property of the *bill*, chosen before any quantity is entered. A
claim row carries a quantity and a rate and **has no leg field of its own**, so
there is no shape in which a mixed-leg bill can be expressed. That is a
stronger guarantee than a UI that merely discourages one. `leg` is not editable
after creation — changing it would re-base every claim against a different
approved figure.

`ra_no` is assigned **server-side on save**, which is what makes "RA5 before
RA4" and "two RA6s" impossible rather than merely rejected: there is no input
to reject.

#### The caps

Both enforced in `ra.clean_claims()`, **never in the persistence layer** —
`db.sync()` runs from `teardown_request`, after the response is built, so a cap
there could not reject anything.

| | | |
|---|---|---|
| `MAX_RA_LINES` | `= boq.MAX_LINES` (600) | **derived, not chosen.** The form renders every BOQ line, so a BOQ legal at 600 lines must post an RA bill legal at 600 lines |
| `MAX_RA_JSON_BYTES` | `150_000` | **measured, not copied.** See below |

Measured against the seeded 97-line Sify BOQ (87 priced lines), every line
filled: **6,896 bytes decoded = 79.3 B/line**, 11,084 on the wire = 127.4 B/line
(**1.61× expansion**). A BOQ line is 701 B, so an RA line is ~8.8× smaller — it
carries no specification text. The expansion is *worse* than the BOQ's
1.36–1.51× because an RA line is almost all punctuation and short numerals with
no prose to dilute the percent-escaping, which is exactly why the constant is
measured rather than scaled. At the line cap that is 46 KB decoded / 75 KB on
the wire, and 150,000 × 1.61 = 241,500 leaves ~258 KB of Flask's 500,000
`MAX_FORM_MEMORY_SIZE` for the other fields.

#### Escaping

`_alert()` escapes its own message and **every caller passes plain text**.
That is the choke point rather than a convention: `overclaim_message()`
interpolates an item number, and `item_no` is free text typed on the BOQ form,
so `<script>` in a line's item number reaches this banner. It did, until this
escaped it — there is a test.

---

### `/address` — Address Book · [address.py](address.py)

| Route | View |
|---|---|
| `GET /address/` | `list_addresses` |
| `GET,POST /address/add` | `add_address` |
| `GET,POST /address/edit/<id>` | `edit_address` |
| `GET /address/delete/<id>` | `delete_address` |

Indian postal format, rendered top-to-bottom by `format_address_lines()`:
contact/company → line1 (building) → line2 (street) → landmark →
`City - PIN` → `State, India`.

`_validate(form)` returns `(data, error)` and **always returns data**, so a
rejected form re-renders with the user's input intact. Both add and edit share
`_render_form()`. **Six** demo addresses seed on first visit via
`ensure_demo_addresses()` — three customer-side (Mumbai office / Pune site /
Ahmedabad delivery) that feed the quotation's Bill To and Ship To pickers, and
**three vendors** that feed the purchase order form. The buy side has to have
somebody to buy from; without them the PO vendor picker opens empty and the
module looks broken on a fresh install.

This module reuses `PRODUCT_STYLES` for its forms and tables — so product CSS
changes affect address pages too.

**It exports the pickers both other modules use:** `picker_options()` and
`picker_payload()`. This is a real dependency, despite what its own docstring
says (§8).

`picker_options(placeholder, only_types=None, selected="")` — `only_types`
narrows the list to given address types, which is how the PO form offers
**vendors only** and cannot suggest a customer's site as somebody to buy from.
Omitted, it returns the whole book, which is what the quotation's pickers want.
Note the "Other" orphan group is **suppressed when filtering**: an address whose
type is not in `ADDRESS_TYPES` is being rescued from disappearing, not offered
as a match for a filter it does not satisfy.

---

### `/settings` — Company Identity & Bank Details · [settings.py](settings.py)

| Route | View |
|---|---|
| `GET,POST /settings/` | `edit_settings` |

One form, two sections: **Company Identity** (legal name, tagline, address,
phone, e-mail, web, GSTIN, PAN, branches, signatory) and **Bank Details** (bank,
account name, account number, IFSC, branch). Reached from the **Settings link in
`_nav()`**, so it is one click from anywhere.

`branding.py` values are the **defaults**; this page saves *overrides*.

```
POST /settings/  →  STORE["settings"]["company"] = {only non-default values}
                 →  branding.apply_settings(overrides)
                 →  next render picks them up. No restart.

app.py boot      →  db.load_into(STORE)
                 →  B.apply_settings(settings.load_saved())
```

#### The one rule that makes this work

**Read company fields through the module — `B.COMPANY_ADDR`, never
`from branding import COMPANY_ADDR`.** A from-import binds a copy at import
time and freezes on the default forever, so no saved setting can ever reach it.
`quotation.py` did exactly that (a block of `COMPANY_ADDR = B.COMPANY_ADDR`
re-exports) and was converted when this page was added. If you add a company
field, do not copy it to a local.

`COMPANY_NAME` and `COMPANY_SHORT` are deliberately **not** editable: the name
is painted two-tone by `name_html()`, baked into the logo artwork and used to
build `_BRANCHES` at import; the short form seeds reference numbers. Changing
either is a rebrand, not a setting.

#### Behaviours worth keeping

- **Every field is optional.** Blank falls back to the `branding.py` default and
  prints as an amber `todo-chip`. That is the existing, deliberate contract: a
  missing statutory detail must be *visible*, never silently empty.
- **Clearing a field restores the default** rather than saving a blank —
  `apply_settings()` treats blank as "not set".
- **Only non-default values are stored**, so a later edit to `branding.py` still
  reaches anyone who never overrode that field. Clear everything and the record
  is deleted outright.
- **`_validate()` always returns data**, so a rejected form re-renders with the
  user's input intact — same contract as `address._validate()`.
- Validated when non-blank: GSTIN (15-char), PAN (10-char), IFSC (11-char),
  account number (9–18 digits), e-mail, phone. GSTIN / PAN / IFSC are stored
  **upper-cased**, because that is how they are issued.
- The **nav carries an amber dot** while any of the 15 fields is blank, and the
  dashboard footer nudge links here. Both clear themselves once complete.

---

### `/extractor` — Market News · [extractor.py](extractor.py)

`GET /extractor/` only. A dark-canvas page of **four hardcoded articles** in
`SAMPLE_ARTICLES`. The "+ Add to Quotation" button is a pure CSS toggle — it
does nothing. This page is a visual demo, not a feature. It uses
`B.RED_ON_DARK` variants because the print reds go muddy on near-black.

---

### `pipeline.py` — no routes, all the deal logic

Edit `SALES_STAGES` and everything downstream regenerates (create-form dropdown,
edit panel, register tabs, summary tiles):

```
Budgetary - Stage I → Budgetary - Stage II (default) → Technical → Commercial
→ Negotiation → PO Expected → Closed Won | Closed Lost
```

Public surface: `ensure_fields`, `stage_of`, `is_won/lost/closed/open`,
`apply_update(q, form)`, `filter_quotations`, `summarize`, `log_event`,
`stage_badge`, `po_cell`, `history_html`, `PIPELINE_STYLES`,
plus the shared utilities `esc`, `parse_money`, `fy_of`, `fy_ref`,
`GST_STATE_CODES`, `state_of_gstin`, `gstin_state_label`.

- `GST_STATE_CODES` / `state_of_gstin()` / `gstin_state_label()` read the State
  out of a GSTIN's first two digits — `gstin_state_label()` returns it Rule
  46(n) style, `'Maharashtra (27)'`, or `''` when the GSTIN is blank or
  unreadable. They live here for the same reason `fy_of` does: **both chains
  print a party's State and neither may import the other.** `invoice.py` still
  carries its own copy of the same table (`invoice.GST_STATE_CODES`,
  `_supplier_state()`); collapsing the two is a one-line change nobody has made
  yet, and until somebody does, an added State belongs in **both**.

- `apply_update()` **stages** changes and validates before committing, so a
  failure never half-writes. It only touches keys actually present in the form,
  so a stage-only post won't blank a recorded PO.
- `REQUIRE_PO_FOR_WON` (default `False`) — flip to `True` to forbid Closed Won
  without a customer PO number.
- `parse_money()` is lenient: accepts `12,50,000`, `₹ 1250000`, `''`. Returns
  `0.0` rather than raising, because a typo shouldn't lose the rest of the edit.

---

## 6. Branding — `branding.py`

Everything client-specific lives here. **No other module should hardcode a
company name, hex colour, or image path.**

⚠ **The identity values here are defaults, not the live values.** `/settings`
overrides them at runtime (§5). Always read them as `B.COMPANY_ADDR` —
`from branding import COMPANY_ADDR` binds a copy at import and will never see a
saved setting. `SETTINGS_KEYS`, `DEFAULTS`, `apply_settings()` and
`current_settings()` in §1c are that mechanism.

`COMPANY_PHONE` (`8898420303`) and `COMPANY_EMAIL`
(`samruddhifire@gmail.com`) are filled in — they feed the dashboard footer strip
and the quotation letterhead contact block
([quotation.py:2447-2448](quotation.py#L2447-L2448)).

⚠ **These ship blank** and render as amber "add …" chips on screen *and on the
printed documents*, so nothing goes out silently wrong. They are now fillable
from **/settings** rather than by editing this file:

```
COMPANY_LEGAL · COMPANY_ADDR · COMPANY_WEB
COMPANY_GSTIN · COMPANY_PAN · COMPANY_BRANCHES
BANK_NAME · BANK_ACCOUNT_NAME · BANK_ACCOUNT_NO · BANK_IFSC · BANK_BRANCH
```

The `BANK_*` block (§1b) exists for the **proforma invoice only**. A PI is a
request for money, so the remittance account has to print on it — a PI without
one is not actionable by the customer's accounts department. They are
deliberately **not** used on the quotation or the tax invoice: a quotation is an
offer, and a tax invoice records a supply that was normally already paid for
against the PI. Publishing the account number wider than necessary is a fraud
surface.

⚠ **`COMPANY_GSTIN` is now load-bearing, not just letterhead decoration.**
`invoice._supplier_state()` reads its first two digits to work out which State
we supply from, which is what powers the IGST-vs-CGST warning. A blank or
specimen GSTIN silently disables that check — it does not fail loudly, because a
half-configured demo must still render. Set the real one at `/settings` before
the first tax invoice.

The dashboard's footer nudge is keyed on `COMPANY_ADDR/PHONE/EMAIL` together
(`_footer_contact()`), and the nav's amber dot on **all 15** settings fields
(`_nav()`). Both link to `/settings` and clear themselves.

`COMPANY_TAGLINE` ("Fire Protection Systems & Services") is an **assumption**
drawn from the trading name — confirm the client's actual letterhead wording.

### Chart palette — `CHART_*` (§2b)

The dashboard's charts draw from here, and the values are **validated, not
picked by eye**:

- **`CHART_NAVY`** — a 6-step *ordinal* ramp at the brand navy hue (OKLCH
  h=307°), light→dark, for the sales funnel. The lightest step is held at
  2.09:1 on white so it cannot dissolve into the surface.
- **`CHART_WON` / `CHART_LOST` / `CHART_SERIOUS` / `CHART_WARN`** — the reserved
  *status* scale (good / critical / serious / warning). Never reuse these for a
  plain data series, and always pair them with a word or an icon.
- **`CHART_TOKENS`** — the CSS custom properties, kept **out of `CSS_TOKENS`**
  so the printed quotation and the other pages don't carry a palette they never
  draw with. `DASH_STYLES` injects it.

The ramp passes monotone-lightness, adjacent-ΔL and light-end contrast; the
status trio passes the lightness band, chroma floor, CVD separation (worst
adjacent pair ΔE 20.3 under protanopia) and 3:1 contrast on the light surface.
**If you change a hex here, re-run the validator** — don't eyeball it.

Artwork is inlined via `_data_uri()`. `LOGO_URI` (64px, nav) and `LOGO_DOC_URI`
(256px, letterhead) are separate on purpose; the favicon is a 32px PNG rather
than the `.ico`, because the `.ico` carries every size to 256 and would add
~68 KB of base64 to **every** page.

---

## 7. Known gaps & rough edges

Real, verified, and safe to pick up:

1. **No dependency pinning.** `requirements.txt` carries lower bounds only, and
   there is no lockfile or virtualenv — installs land in whatever interpreter is
   on `PATH`. It covers the **runtime only**: `pytest` to run `tests/` and
   `openpyxl` to regenerate `demo_data.py` are not in it. Node is optional —
   `tests/test_picker_js.py` runs the BOQ picker's real JavaScript when it is
   installed and skips when it is not.
2. **No product edit route** — delete + re-add only, and delete may be blocked.
   ⬆ **This got more expensive.** It is now the reason a missing HSN cannot be
   blocked at the tax invoice (a user could not clear the block), and the reason
   `_seed()` has to backfill. An edit route is the highest-value gap on this
   list.
   ⬆ **Still open, and now also duplicated.** `spec.py` ships an edit route and
   the `_render_form` / always-return-data pattern that `product.py` wants; port
   it across when that file can next be touched. *(Note: This condition is not currently met. Editing `product.py` is absolutely forbidden per [INTRODUCTION.md §7](INTRODUCTION.md), so do not attempt to port it across yet.)* `spec._valid_tax_code()` is a
   deliberate copy of `product._valid_hsn()` for the same reason — the shared
   home is `pipeline.py`, and moving it means editing `product.py`. Fold the two
   together in the same pass.
3. **No quotation edit / delete / amend flow**, though `amend_no` is stored.
   Likewise **no cancel/void route for a proforma invoice** — an issued PI can
   only be superseded by raising another. A void flow (a `cancelled` flag plus
   a CANCELLED overprint, never a hard delete, so the number is never reused)
   is the right shape when it is wanted.

   ⚠ **For a tax invoice this is no longer just inconvenient.** A wrong tax
   invoice cannot be corrected by editing it — GST requires a **credit note**
   (or debit note) referencing the original invoice number, and those are
   reported separately in GSTR-1. Deleting the record instead would leave a
   hole in a serial the law requires to be consecutive. **A credit-note flow is
   the next real piece of work in this chain.**
4. ~~**`hsn` is read in 9 places but never captured.**~~ **Fixed** — captured on
   the add-product form, validated, backfilled onto the seeded rows, and
   carried down the whole chain. What remains: **the seeded HSN codes are
   placeholders**, plausible chapter headings rather than a classification
   Samruddhi's CA has signed off. Getting one wrong is the customer's ITC.
   Have all twelve reviewed before a tax invoice goes out.
5. **`quotation._next_ref()` = `len(quotations) + 1`** → `QT-0001`. Collides
   after a deletion, isn't year-scoped, and ignores `COMPANY_SHORT = "SF"`.
   `proforma._next_ref()` fixes the collision half (max+1); porting that back
   to `quotation.py` is a two-line change.
6. **404 and 500 both redirect to the dashboard.** Great for a stakeholder demo,
   painful while developing — a real traceback becomes a silent redirect. Comment
   the handlers out in `app.py` when debugging.

   **413 deliberately does not.** A 404 is a mistyped URL and nobody's work; a
   413 is a form somebody spent an afternoon on, and bouncing them to the
   landing page would look exactly like the app discarding it without comment.
   `dashboard.too_large_page()` renders a real page — app.py wires it and does
   not build it, as ever — with the nav still on it, an honest statement that
   the input could not be recovered (Werkzeug rejects the body *before* the
   form is parsed, so `request.form` is empty by construction), and a pointer
   at the Back button, which may still hold it. **The status stays 413**: a 302
   would tell the browser, the logs and any future API client that an oversize
   POST succeeded. It imports `boq.MAX_LINES` *inside the function* — boq.py
   imports dashboard.py, so a module-level import is a cycle — rather than
   hardcoding 600 where it would drift from the constant that enforces it.
7. **HTML escaping is inconsistent.** `address.py`, `pipeline.py` and
   `proforma.py` escape; `quotation.py` and `product.py` largely don't.
8. **`SECRET_KEY` defaults to `qms-demo-secret-2024`.** Generate a real one
   before any deployment.
9. **Standing T&C clauses are unreviewed** by the client — all three of
   `quotation._build_tnc()`, `proforma._build_pi_terms()` and
   `invoice._build_ti_terms()` (§5).

9b. **No e-invoicing (IRN + signed QR code).** Mandatory under Rule 48(4) once
   aggregate turnover crosses **₹5 crore**, and from **1 April 2026** that
   threshold applies broadly. It means registering each invoice with the
   Invoice Registration Portal and printing the IRN and the signed QR it
   returns — an API integration with credentials and a JSON schema, not a page.
   Until then, an invoice out of this app is a valid manual tax invoice for a
   below-threshold supplier and **not** valid for one above it. Confirm
   Samruddhi's turnover before relying on it.

   The same threshold decides **HSN digits** (4 up to ₹5 cr, 6 above). The app
   validates shape only and does not enforce a length, because it does not know
   the turnover — see `product._valid_hsn()`.

9d. 🟠 **Server-side template injection — OPEN in two modules.**
   A view that ends with `render_template_string(template)` on a string that is
   **already fully interpolated** parses it a second time. Nothing is passed as
   Jinja context (§1 says so), so that second parse buys nothing — but
   `pipeline.esc()` escapes `< > & " '` and deliberately **not** braces, so any
   `{{ … }}` that reached the output from user input is executed.

   Demonstrated on the spec library before it was fixed there: a clause reading
   `{{ config }}` printed the Flask config **including `SECRET_KEY`**, and one
   reading `{% for x in y %}` raised a `TemplateSyntaxError` that 500'd every
   page carrying that text — a stored denial of service, since the BOQ form
   embeds all 56 clauses.

   **Where the fix reaches, it is one line per module**: return the finished
   string instead of re-rendering it. Flask returns any `str` a view returns.
   Each fixed module carries a `_page()` helper whose sole job is to be the
   place that comment lives.

   ```python
   -    return render_template_string(template)
   +    return _page(template)          # returns html unchanged
   ```

   ✅ **Fixed in `spec.py` and `boq.py`** (first pass), and in **`proforma.py`,
   `invoice.py`, `purchase.py`, `address.py`, `settings.py`, `dashboard.py`**
   (second pass — 13 call sites, `render_template_string` dropped from all six
   imports). Guarded by [tests/test_ssti_group1.py](tests/test_ssti_group1.py):
   per module, a stored `{{ config }}` must render literally and must not leak
   the app's actual `secret_key`, and a stored `{% for x in y %}` must not take
   the page down. Every assertion runs against the **rendered page**, and a
   control test proves the payload genuinely reached it — 18 of those 19 fail
   against the code as it was.

   🔴 **Still open in `quotation.py` and `product.py`, and the one-liner does
   not reach either.** `quotation.py` builds its pages with `.format()` rather
   than f-strings and has attribute, `<script>` and option-text sinks besides;
   `product.py` has no escaping at all in 1409 lines, so returning the string
   unrendered fixes the injection and leaves the XSS. Each needs its own pass,
   and `product.py`'s is really an escaping pass (§7.7) with this fix on the
   end.

9e. 🔴 **User text inside `<script>` — OPEN wherever `json.dumps` is embedded.**
   `json.dumps` does not escape `<`, so a value containing `</script>` closes
   the block and everything after it parses as HTML. `boq._json_for_script()`
   fixes it for the three payloads on the BOQ form (`<` / `>` /
   `&` are ordinary JSON escapes, so the browser decodes them back
   unchanged). The same raw pattern is still used by
   `quotation._product_catalog_json()` and by every
   `json.dumps(picker_payload())` on the quotation form. Same reason for
   leaving it, same size of fix.

9c. **No GSTR-1 export and no HSN-wise summary.** The register totals output tax
   but nothing produces the return-shaped extract, and the printed sheet carries
   HSN per line without the consolidated HSN summary a return wants.

**Buy side (`purchase.py`), all real and all deliberate for now:**

14. **No goods-receipt note (GRN) and no partial-quantity tracking.** "Partially
    Received" is a status somebody sets by hand, not a computed state — nothing
    records *which* lines came in or how many. Per-line received quantities are
    the natural next step, and are what would make the status honest.
15. **No supplier-invoice matching.** The classic three-way match (PO ↔ GRN ↔
    supplier invoice) is the point of a purchasing module in an accounting
    system, and none of it exists. Input tax credit is claimed off the
    supplier's invoice, which this app never sees.
16. **No PO edit, amend or revision.** Status is the only mutable field, by
    design (an issued PO's numbers should not move behind the vendor). But there
    is no amendment flow either, so a price change means a fresh PO with no link
    to the one it supersedes — the same shape of gap as §7.3 on the sell side.
17. **Free-text line items are not possible.** Every PO line must be a catalogue
    product. Real purchasing buys consumables, freight and one-off fabrication
    that will never be in a sales catalogue. An "other — describe it" row is the
    fix.
18. **Job costing is material only.** No labour, no overhead, no allocation of a
    stock purchase across the jobs that consume it. The margin figure on the
    deal panel is a gross material margin and nothing more; the panel says so,
    but it is easy to quote at somebody as if it were profit.
19. **Vendor addresses are the only vendor record.** There is no vendor master —
    no payment terms, no lead time, no ratings, no GSTIN validation at the point
    of purchase. `type: "vendor"` in the address book is carrying that whole
    concept.

10. ⚠ **The seeded company identity is SPECIMEN DATA, not Samruddhi's.**
    `settings.ensure_demo_settings()` writes a demo record into
    `STORE["settings"]["company"]` at boot so the documents render without
    amber chips. The statutory identifiers are deliberately template patterns
    and the bank is named so nobody can mistake them for real:

    > **Corrected.** This section used to say the identity was *loaded*. It was
    > not — it had been hand-entered into one working database and never
    > seeded, so it existed on exactly one machine and dropping that database
    > took the letterhead, GSTIN, PAN and the whole bank block with it. The
    > seeder was added in the hardening pass; `DEMO_COMPANY` in `settings.py`
    > is now the source of the table below.

    | Field | Loaded value | Real? |
    |---|---|---|
    | `COMPANY_GSTIN` | `27AAAAA0000A1Z5` | **no — all-A/all-zero template** |
    | `COMPANY_PAN` | `AAAAA0000A` | **no — template** |
    | `BANK_NAME` | `SPECIMEN BANK LTD.` | **no** |
    | `BANK_ACCOUNT_NO` | `50200000000000` | **no — trailing zeros** |
    | `BANK_IFSC` | `SPEC0000000` | **no** |
    | `COMPANY_ADDR` | Unit 7, Ganesh Industrial Estate… | **no — invented** |
    | `COMPANY_LEGAL` | M/s Samruddhi Fire Services | unconfirmed guess |
    | `COMPANY_WEB` | www.samruddhifire.in | **unverified — may not exist** |
    | `COMPANY_PHONE` / `COMPANY_EMAIL` | 8898420303 / samruddhifire@gmail.com | yes |

    **Replace every one of these at `/settings` before a document goes to a
    customer.** Because the fields are now filled, the amber-chip safety net
    that used to catch this is switched off — which is exactly why it is
    recorded here instead.

    ⚠ **A tax invoice raises the stakes on this.** `COMPANY_GSTIN` is a
    template pattern, so `27AAAAA0000A1Z5` would print as our GSTIN on a
    statutory document — and its `27` prefix is what
    `invoice._supplier_state()` currently reads as "Maharashtra". The
    IGST-vs-CGST warning is therefore being computed from **specimen data**
    until the real GSTIN is entered.
11. **Seed prices are placeholders**, not Samruddhi's real rates.
12. **The printed document has no page numbers.** "Page 1 of 2" needs a page
    counter, and Chrome does not support `@page { @bottom-right { content:
    counter(page) } }`. The old hardcoded `Page 1 of 1` was removed rather than
    left to print a wrong number on every page. Real page numbers, and a
    "Quotation No. / Date" strip on continuation pages, need a server-side
    renderer (WeasyPrint or wkhtmltopdf) instead of browser print.

    This bites hardest on the tax invoice's `?copy=all`, which is three full
    sheets in one print run with nothing but the `.copy-mark` caption to tell a
    reader which copy a loose page belongs to. A server-side renderer would fix
    the copy captions and the page numbers together, and is the single change
    that would most improve all three documents.
13. **`app.run(debug=True)`** with `reloader_type="stat"` — the stat reloader is
    intentional (the watchdog reloader storms on Windows when AV/indexers touch
    `site-packages`). Never ship `debug=True`.
14. **The RA bill's tax block is not per-line, despite the record being.**
    `build_claim()` snapshots `gst_rate` onto every claim row and
    `compute_tax_totals()` never reads it — it applies the **bill-level**
    `cgst_rate` / `sgst_rate` / `igst_rate` to every line and sums. On a
    single-rate bill (all twelve lines of `SF/RA/26-27/0001` are 18%) the answer
    is right; on a bill mixing 18% goods with 12% or 5% work it is wrong, and
    wrong on a statutory document. §2b says the load-bearing reason `ra.py` may
    not import `invoice.py` is that *"the RA bill's tax block is per-line"* —
    the record shape delivers that and the arithmetic does not yet.
15. **`/ra/print` hardcodes the supplier's state, and prints no place of
    supply.** `seller_state = "Punjab (03)"` and a fallback GSTIN of
    `03AAACS2024F1Z0` are literals in `print_ra()`, contradicting
    `settings.py`'s own `COMPANY_GSTIN` (whose placeholder is a `27`/
    Maharashtra pattern — see gap 10). **Place of supply with its State code is
    a Rule 46 field and is absent from the document entirely.** It is also what
    decides CGST/SGST versus IGST: the seeded bill is Punjab → Karnataka, an
    inter-state supply, and it prints CGST+SGST because `tax_type` defaults to
    `cgst_sgst` and no form offers the choice. `invoice.py` already derives this
    (`_supplier_state()`, `pos_code`) — but `ra.py` may not import it, so the
    derivation has to be grown here or lifted into `pipeline.py`.
16. **`bill_gstin` is blank on the seeded BOQ**, so the customer GSTIN prints as
    an em dash on `SF/RA/26-27/0001`. Rule 46 requires the recipient's GSTIN
    where they are registered. This is missing demo data rather than a code
    fault, but it is missing on the record a demo will be given from.

---

## 8. Stale docs — do not trust these two files

Both are leftover scratch files. **Neither is imported by anything**
(verified: no import of `integration` or `product_view_additions` exists).

- **`integration.py`** — 131 lines of docstring describing how to wire
  `quotation.py` in. Its URL map is out of date, and it documents an
  **`expand_product(product_id, qty, depth, visited)` recursive expansion
  engine that does not exist in the codebase.** The real flattening is
  `_process_selections()` in `quotation.py`, driven by browser JS, and it only
  produces two depths. Do not implement against this file.
- **`product_view_additions.py`** — a "paste these four blocks into product.py"
  patch file. Those blocks are **already applied**. Its `VIEW_STYLES` is a
  duplicate of the live one in `product.py`.

Also stale, *inside otherwise-live files*:

- `address.py` docstring claims "nothing else in the app reads
  `STORE["addresses"]`" and "in-memory only, lost on restart". Both are now
  false — `quotation.py` imports `picker_options`/`picker_payload`, and `db.py`
  persists the `addresses` collection.

Both `dashboard.py` entries that used to sit here (the "not wired into
quotations" card label and the "stub routes" docstring) are **fixed** — that
file's docstring and card copy now describe what it actually does. The dead
`header.hero`, `.hero-logo`, `.stub-*`, `.card-arrow` and `section.grid` rules
they left behind have been removed from `BASE_STYLES`, so every page carries a
little less CSS.

---

## 9. Conventions to follow when adding code

- **New feature = new blueprint module**, registered in `app.py`. Keep `app.py`
  as wiring only.
- **Decide which pipeline it belongs to first.** If it is about money coming in
  it is sell side and may join the quotation → PI → TI chain. If it is about
  money going out it is buy side and must not touch a PI or a TI. If both need
  a helper, it goes in `pipeline.py`, which imports nothing from the app.
- Import `BASE_STYLES` and `_nav` from `dashboard`, layer your own `<style>`
  block after them.
- Pull every company string, colour, and image from `branding.py`.
- Cross-blueprint links use `url_for("blueprint.view_function")`.
- Flash messages are query params: `redirect(url_for(..., msg="...",
  type="success"|"error"))`, rendered as `.alert .alert-success/-error`.
- New persisted collection? Add the key to `STORE` **and** to
  `db.COLLECTIONS` — the table is then created automatically on next start.
- Business rules that might change belong in a module-level constant with a
  comment (see `REQUIRE_PO_FOR_WON`), not buried in a branch.
- Money **on screen** renders as `&#8377;&nbsp;{v:,.0f}`. Money **on the
  printed document** goes through `_inr()` — Indian digit grouping, no symbol.
  Do not mix them. Quantities use `_fmt_qty()` (drops a trailing `.0`).
- Remember the doubled braces in f-string HTML.
