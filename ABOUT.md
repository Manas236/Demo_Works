# ABOUT — Samruddhi Fire QMS

> **Read this file at the start of every conversation before touching code.**
> It is the project's context anchor: what this app is, how each page works,
> where the landmines are, and what is deliberately unfinished.
> If you change architecture, a data shape, or a route — update this file in the
> same commit.

---

## 1. What this is

A **Flask quotation & catalogue system for Samruddhi Fire**, a fire-protection
contractor in India. It is a **seller-side** app: we build the catalogue, we
price it, we issue the quotation, we raise the proforma invoice against it, and
we record the customer's incoming Purchase Order. We never issue POs here.

The document chain is **quotation → proforma invoice**. A tax invoice is *not*
issued by this app; the PI explicitly says so on its face.

Run it:

```bash
python app.py          # http://127.0.0.1:5000
```

Dependencies (there is **no requirements.txt** — see §7):
`flask`, `pymysql`, `python-dotenv`, `markupsafe`.

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
- `render_template_string` still runs Jinja over the result, so `{{ }}` that
  survives into the output will be interpreted as Jinja. Values are
  pre-interpolated by Python, not passed as Jinja context.
- User-supplied text is **not** auto-escaped in most places. `address.py` uses
  `markupsafe.escape` via `_e()`; `pipeline.py` uses `esc()`. `quotation.py`
  and `product.py` mostly do not. Treat this as a known gap, not a pattern to
  copy.

---

## 2. Module map

| File | Lines | Role |
|---|---|---|
| [app.py](app.py) | 87 | Wiring only. Boots persistence, registers blueprints, error handlers. Never implements features. |
| [store.py](store.py) | 35 | The `STORE` dict. Single shared object, imported everywhere. |
| [db.py](db.py) | 295 | MySQL persistence by snapshot-and-diff. |
| [branding.py](branding.py) | 251 | Company identity, bank details, colour palette, chart palette, logo data URIs. |
| [dashboard.py](dashboard.py) | 1159 | Operations dashboard **+ `BASE_STYLES` and `_nav()` that every other module imports**. |
| [product.py](product.py) | 1271 | Product catalogue + assemblies (BOM). |
| [quotation.py](quotation.py) | 2693 | Quotation form + printed document. The big one. |
| [proforma.py](proforma.py) | 1043 | Proforma invoice, derived from a quotation. Reuses the quotation's document sheet. |
| [pipeline.py](pipeline.py) | 491 | Sales stages, customer PO, win/loss. Pure logic, no routes. |
| [address.py](address.py) | 888 | Address book + the picker that quotations use. |
| [extractor.py](extractor.py) | 407 | "Market News" page. **Hardcoded dummy data**, dark theme, decorative. |
| `integration.py` | 131 | **Dead file.** Stale docs only — see §8. |
| `product_view_additions.py` | 495 | **Dead file.** Stale docs only — see §8. |

**Import direction (never reverse these — circular imports):**

```
app.py
 ├─ dashboard.py ──────────────┐  (BASE_STYLES, _nav) imports branding, store, pipeline
 ├─ product.py ────────────────┤  imports dashboard, branding, store
 ├─ address.py ────────────────┤  imports dashboard, branding, store, product (PRODUCT_STYLES)
 ├─ quotation.py ──────────────┤  imports dashboard, branding, store, address, pipeline
 ├─ proforma.py ───────────────┤  imports dashboard, branding, store, pipeline, quotation
 └─ extractor.py ──────────────┘  imports branding only

pipeline.py imports nothing from the app  ← keep it that way
branding.py imports nothing from the app  ← keep it that way
```

`quotation.py → pipeline.py`, **never** the reverse.

`proforma.py → quotation.py`, **never** the reverse. proforma imports the
document's formatters and stylesheet (`_inr`, `_fmt_qty`, `_amount_in_words`,
`_meta`, `VIEW_DOC_STYLES`, `QUOTATION_STYLES`) so the two documents cannot
drift apart. The quotation view page links *to* proforma with
`url_for("proforma.…")` and reads `STORE["proformas"]` directly — a `url_for`
string needs no import, which is what keeps the arrow one-way.

**dashboard.py may import `branding`, `store` and `pipeline`** — none of those
import anything from the app, so there is no cycle. It must **never** import
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
    "addresses":    {},     # uuid -> address
    "_seeded":      False,  # product seeder guard
    "_addr_seeded": False,  # address seeder guard
}
```

### Product

```python
{
  "id": uuid, "name": str, "part_no": str, "unit": str,
  "base_price": float, "description": str,
  "type": "standalone" | "assembly" | "support",
  "children": [ {"product_id": uuid, "qty": int}, ... ],   # assemblies only
}
```

- `assembly` = has children (a BOM). `support` = a sub-component not sold
  alone. `standalone` = sold on its own. Only the badge and the picker treat
  these differently; nothing enforces that `support` items stay inside
  assemblies.
- **`hsn` is read but never written.** `quotation.py` reads `p.get("hsn", "")`
  in 9 places, but the add-product form has no HSN field, so it is always `""`.
  Adding an HSN input to `add_product()` is a real, small, valuable task.

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

Three properties this shape exists to guarantee:

1. **The snapshot is frozen.** `line_items` is copied, not referenced. A
   shallow `dict(row)` per line is sufficient — every value in a `line_item` is
   a scalar. Editing the source quotation afterwards cannot reach an issued
   invoice, which is the whole reason a PI is its own record.
2. **`quotation_ref` is stored, not looked up.** The PI still prints correctly
   as a historical document if the quotation is ever removed.
3. **`amount_due + balance_due == grand_total`**, always. `amount_due` is the
   figure the customer actually has to pay now; `advance_pct` is only how it
   was derived.

Many PIs may point at one quotation (advance, then balance, then a part
supply). Nothing enforces that their amounts sum to the quoted value — that is
a judgement call for whoever raises them, and the convert form shows the PIs
already issued against that quotation so the decision is an informed one.

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
              serialise each record → compare to last-written digest
              → upsert changed, delete missing
```

- One table per collection (`products`, `quotations`, `proformas`,
  `addresses`), each row is
  `id VARCHAR(64) PK, data JSON, updated_at TIMESTAMP`. The **whole record is a
  JSON document** — chosen because quotation shape is still moving and columns
  would mean a migration per field.
- Trade-off: MySQL cannot query *inside* a quotation. When reporting needs it,
  promote hot fields (`ref`, `sales_stage`, `grand_total`) to generated columns;
  the JSON stays authoritative.
- `teardown_request` (not `after_request`) so a half-finished mutation is saved
  even when a view raised.
- `sync()` **never raises**. On failure it flips to in-memory and prints
  `!! persistence lost:`. If data stops saving, look for that line.
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
7. **Module strip** — the old card launcher (5 cards: catalogue, quotations,
   proforma invoices, address book, market news), now at the foot, carrying
   live counts instead of prose. The strip is `auto-fit`, so adding a card
   needs no layout change.

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

**Add page.** Fields: name, part_no, unit (dropdown), base_price, description,
type. Choosing **Assembly** reveals a vanilla-JS child editor (repeating
`child_product_id` / `child_qty` rows).

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

Validation, in order: quotation exists → date present → `advance_pct` parses →
`0 < pct <= 100` → validity is digits. A rejected POST re-renders with the
user's own input (`_v()` prefers `request.form`, then the quotation's value,
then the module default), and nothing is written to STORE.

On success it writes the record, calls `P.log_event()` on the **quotation** —
raising a PI is a real event in the deal's life and belongs on its audit trail,
though it deliberately does not change the sales stage — and redirects to the
document.

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
- **`.pay-box`** — Total invoice value → **Amount Payable Now** → balance, then
  the payable-now figure in words. It is **only rendered when `advance_pct <
  100`**; when the PI asks for the full value the closing row of the table
  already says it, and printing the same number twice invites the reader to
  hunt for a difference. The payable-now figure carries the heavy rule and the
  `--fs-md` step — the same emphasis the closing total gets, and no more.
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
not year-scoped — that needs the client's real numbering policy
(`SF/PI/26-27/0001` is the usual shape).

#### Business rules — module-level constants, not buried in branches

`DEFAULT_ADVANCE_PCT` (100 — asking for less must be deliberate),
`DEFAULT_PI_VALIDITY` (15 days, shorter than a quotation's on purpose),
`ADVANCE_PRESETS`, `_REF_PREFIX`.

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
`_render_form()`. Three demo addresses (Mumbai / Pune / Ahmedabad) seed on first
visit via `ensure_demo_addresses()`.

This module reuses `PRODUCT_STYLES` for its forms and tables — so product CSS
changes affect address pages too.

**It exports the quotation picker:** `picker_options()` and `picker_payload()`.
This is a real dependency, despite what its own docstring says (§8).

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
`stage_badge`, `po_cell`, `history_html`, `PIPELINE_STYLES`.

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

`COMPANY_PHONE` (`8898420303`) and `COMPANY_EMAIL`
(`samruddhifire@gmail.com`) are filled in — they feed the dashboard footer strip
and the quotation letterhead contact block
([quotation.py:2447-2448](quotation.py#L2447-L2448)).

⚠ **These are still blank** and render as amber "add …" chips on screen *and on
the printed quotation*, so nothing goes out silently wrong:

```
COMPANY_LEGAL · COMPANY_ADDR · COMPANY_WEB
COMPANY_GSTIN · COMPANY_PAN · COMPANY_BRANCHES
BANK_NAME · BANK_ACCOUNT_NAME · BANK_ACCOUNT_NO · BANK_IFSC · BANK_BRANCH
```

The `BANK_*` block (§1b) exists for the **proforma invoice only**. A PI is a
request for money, so the remittance account has to print on it — a PI without
one is not actionable by the customer's accounts department. They are
deliberately **not** used on the quotation: a quotation is an offer, not a
demand for payment, and publishing the account number wider than necessary is a
fraud surface.

The dashboard's amber "identity incomplete" nudge is keyed on
`COMPANY_ADDR/PHONE/EMAIL` together ([dashboard.py:358](dashboard.py#L358)), so
it stays visible until the address is filled in too.

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

1. **No `requirements.txt`.** Needs `flask`, `pymysql`, `python-dotenv`,
   `markupsafe`.
2. **No product edit route** — delete + re-add only, and delete may be blocked.
3. **No quotation edit / delete / amend flow**, though `amend_no` is stored.
   Likewise **no cancel/void route for a proforma invoice** — an issued PI can
   only be superseded by raising another. A void flow (a `cancelled` flag plus
   a CANCELLED overprint, never a hard delete, so the number is never reused)
   is the right shape when it is wanted.
4. **`hsn` is read in 9 places but never captured** — always empty on the
   document.
5. **`quotation._next_ref()` = `len(quotations) + 1`** → `QT-0001`. Collides
   after a deletion, isn't year-scoped, and ignores `COMPANY_SHORT = "SF"`.
   `proforma._next_ref()` fixes the collision half (max+1); porting that back
   to `quotation.py` is a two-line change.
6. **404 and 500 both redirect to the dashboard.** Great for a stakeholder demo,
   painful while developing — a real traceback becomes a silent redirect. Comment
   the handlers out in `app.py` when debugging.
7. **HTML escaping is inconsistent.** `address.py`, `pipeline.py` and
   `proforma.py` escape; `quotation.py` and `product.py` largely don't.
8. **`SECRET_KEY` defaults to `qms-demo-secret-2024`.** Generate a real one
   before any deployment.
9. **Standing T&C clauses are unreviewed** by the client — both
   `quotation._build_tnc()` and `proforma._build_pi_terms()` (§5).
   The `BANK_*` fields are blank, so every PI currently prints amber
   "add account number" chips where the remittance details belong.
10. **Seed prices are placeholders**, not Samruddhi's real rates.
11. **The printed document has no page numbers.** "Page 1 of 2" needs a page
    counter, and Chrome does not support `@page { @bottom-right { content:
    counter(page) } }`. The old hardcoded `Page 1 of 1` was removed rather than
    left to print a wrong number on every page. Real page numbers, and a
    "Quotation No. / Date" strip on continuation pages, need a server-side
    renderer (WeasyPrint or wkhtmltopdf) instead of browser print.
12. **`app.run(debug=True)`** with `reloader_type="stat"` — the stat reloader is
    intentional (the watchdog reloader storms on Windows when AV/indexers touch
    `site-packages`). Never ship `debug=True`.

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
