"""
One-off generator: reads sify_boq.xlsx and emits demo_data.py.

Run from the repo root. Regenerate rather than hand-edit demo_data.py.
"""
import re
import uuid
import openpyxl

NS = uuid.UUID("6f0f1b7e-2c31-4b3a-9a1e-5d4c0b7a9e10")   # fixed namespace

SEC_ROWS = {"A": (5, 25), "B": (29, 93), "C": (96, 106)}
SEC_HEAD = {"A": 4, "B": 27, "C": 95}
SKIP = {26, 27, 28, 94, 95, 107, 108}
AREAS = {"A": [("External", "C"), ("L0", "D")], "B": [("T1", "C")], "C": []}

wb = openpyxl.load_workbook("sify_boq.xlsx", data_only=True)
ws = wb["Quotation"]


def cell(r, c):
    v = ws[f"{c}{r}"].value
    return v


def txt(r, c):
    v = cell(r, c)
    return "" if v is None else str(v)


def numv(r, c):
    v = cell(r, c)
    return float(v) if isinstance(v, (int, float)) else None


def item_no(r):
    """Column A as TEXT — 4.0999999999999996 must never become 4.0999…"""
    v = cell(r, "A")
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.10g}"
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


# ── Classify rows into families and singles ─────────────────────────────────
rows = []
for s, (a, b) in SEC_ROWS.items():
    for r in range(a, b + 1):
        if r in SKIP:
            continue
        ino = item_no(r)
        if not ino:
            continue
        rows.append((s, r, ino))

fams = {}      # (sec, parent_no) -> {"spec":.., "row":.., "kids":[(ino,row)]}
singles = []   # (sec, ino, row)
for s, r, ino in rows:
    if numv(r, "E") is None and txt(r, "B"):
        fams[(s, ino)] = {"spec": txt(r, "B"), "row": r, "kids": []}

for s, r, ino in rows:
    if (s, ino) in fams:
        continue
    m = re.match(r"^(\d+)[.\s]?([A-Za-z]|\d+)$", ino)
    key = (s, m.group(1)) if m else None
    if key in fams:
        fams[key]["kids"].append((ino, r))
    else:
        singles.append((s, ino, r))


# ── Titles, categories, codes — CURATED, keyed by defining row ─────────────
from curation import CURATION, CAT_CODES


def identity(row):
    if row not in CURATION:
        raise SystemExit(f"row {row} has no curated identity — add it to curation.py")
    code, title, cat = CURATION[row]
    hsn, sac = CAT_CODES[cat]
    return code, title, cat, hsn, sac


DIM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mm|nb|NB)?\b", re.I)


def variant_of(label, row):
    m = DIM.match(label or "")
    dim = m.group(1) if m else None
    dunit = "mm" if m else ""
    return {
        "label": label,
        "dimension": dim,
        "dim_unit": dunit,
        "unit": txt(row, "F").strip(),
        "default_supply_base_rate": numv(row, "G"),
        "default_install_base_rate": numv(row, "K"),
    }


# ── Build the spec library ──────────────────────────────────────────────────
specs = []           # ordered
spec_by_row = {}     # row -> (code, variant_label)

for (s, ino), fam in fams.items():
    code, title, cat, hsn, sac = identity(fam["row"])
    variants = []
    for kid_no, kid_row in fam["kids"]:
        v = variant_of(txt(kid_row, "B"), kid_row)
        variants.append(v)
        spec_by_row[kid_row] = (code, v["label"])
    spec_by_row[fam["row"]] = (code, None)      # the header row
    specs.append({
        "id": str(uuid.uuid5(NS, code)), "code": code, "title": title,
        "spec_text": fam["spec"], "category": cat,
        "supply_hsn": hsn, "install_sac": sac,
        "supply_gst_rate": 18.0, "install_gst_rate": 18.0,
        "variants": variants,
    })

_seen_single = {}
for s, ino, r in singles:
    spec_text = txt(r, "B")
    norm = re.sub(r"\s+", " ", spec_text).strip().lower()
    if norm in _seen_single:                      # A/17 and B/17 are the same clause
        code = _seen_single[norm]
        spec_by_row[r] = (code, "")
        continue
    code, title, cat, hsn, sac = identity(r)
    _seen_single[norm] = code
    # Rule 1: an unsized item still carries exactly ONE variant.
    specs.append({
        "id": str(uuid.uuid5(NS, code)), "code": code, "title": title,
        "spec_text": spec_text, "category": cat,
        "supply_hsn": hsn, "install_sac": sac,
        "supply_gst_rate": 18.0, "install_gst_rate": 18.0,
        "variants": [{
            "label": "", "dimension": None, "dim_unit": "",
            "unit": txt(r, "F").strip(),
            "default_supply_base_rate": numv(r, "G"),
            "default_install_base_rate": numv(r, "K"),
        }],
    })
    spec_by_row[r] = (code, "")

# ── Build the BOQ line table ────────────────────────────────────────────────
lines = []
for s, r, ino in rows:
    code, vlabel = spec_by_row[r]
    is_header = (s, ino) in fams
    parent = ""
    if not is_header:
        m = re.match(r"^(\d+)[.\s]?([A-Za-z]|\d+)$", ino)
        if m and (s, m.group(1)) in fams:
            parent = m.group(1)

    # The opaque key an RA claim is matched on (boq._line_id). uuid5 off the
    # fixed namespace and the line's SOURCE COORDINATE — section + worksheet
    # row — rather than uuid4, because this file has to stay byte-for-byte
    # reproducible: a random id would rewrite all 97 lines on every
    # regeneration and, worse, a re-seeded demo BOQ would no longer match the
    # claims raised against it.
    #
    # Deliberately NOT keyed on item_no. Section A carries item 17 twice, so an
    # item_no key would collide here in the generator too — which is the whole
    # reason the identifier exists. The row number is unique by construction.
    entry = {"line_id": uuid.uuid5(NS, f"boqline:{s}:{r}").hex[:12],
             "item_no": ino, "parent": parent, "section": s, "spec": code}
    if is_header:
        entry["header"] = True
    else:
        entry["variant"] = vlabel
        areas = {}
        for name, col in AREAS[s]:
            v = numv(r, col)
            if v is not None:
                areas[name] = v
        entry["areas"] = areas
        entry["total_qty"] = numv(r, "E") or 0.0
        entry["s_base"] = numv(r, "G")
        entry["s_pct"] = (numv(r, "H") or 0.0) * 100.0
        entry["s_rate"] = numv(r, "I") or 0.0
        entry["i_base"] = numv(r, "K")
        entry["i_pct"] = 0.0
        entry["i_rate"] = numv(r, "L") or 0.0
        entry["remark"] = txt(r, "N").strip()
    lines.append(entry)

sections = [{"code": s,
             "title": txt(SEC_HEAD[s], "B"),
             "areas": [n for n, _c in AREAS[s]]}
            for s in ("A", "B", "C")]

# ── Emit ────────────────────────────────────────────────────────────────────
import pprint

HEADER = '''"""
demo_data.py — Seed data for the specification library and the demo BOQ
========================================================================
**Data only. This module imports nothing from the app** — not `store`, not
`branding`, not even `pipeline`. It sits at the bottom of the import graph
beside `pipeline.py` and `branding.py`, so `spec.py` and `boq.py` can both read
it and neither can create a cycle.

It is kept out of those two modules because of scale, not taste: 56 specs and a
97-line BOQ table would leave `spec.py` more data than code and push `boq.py`
past 2700 lines. `product.py`'s twelve inline items are a different order of
thing.

WHERE THIS CAME FROM
--------------------
Every clause, every rate and every quantity below was **generated from the
client's own `sify_boq.xlsx`** (the Sify Bangalore project) rather than typed,
so the seeded BOQ reproduces their sheet exactly — all three sections
subtotalling 6177563.30 supply / 3013750.00 installation. Regenerate it from
the workbook rather than hand-editing it.

⚠ THE RATES ARE ONE PROJECT'S FIGURES, NOT A PRICE LIST.
   They are the rates agreed for Sify Bangalore, priced off a rate contract
   from another site ("Mohali Rates") and escalated per line. They seed the
   library as *reference defaults* and are meant to be overridden per project.
   `spec.py` says so on the register and on every spec page.

⚠ THE HSN AND SAC CODES ARE PLACEHOLDERS.
   The source workbook carries none. These are plausible chapter headings
   assigned by category — 7306 for MS pipe, 8481 for valves, 8413 for pumps,
   8537 for panels — and **not a classification anybody's CA has signed off**.
   Getting one wrong costs the customer their input tax credit. Same caveat as
   `product._seed()`'s twelve rows, and it matters more here because a BOQ line
   carries two of them.

SPEC_VARIANTS is the point of the library
-----------------------------------------
Their BOQ item 24 is one paragraph of specification; 24.a-24.i are that same
clause at 200/150/100/80/65/50/40/32/25 mm, each with its own rate and unit.
A spec therefore carries `variants`, always a list, never null: an unsized item
(a flow switch, a liaisoning charge) carries exactly one variant with an empty
label and no dimension, so there is one code path rather than two.
"""

# Generated from sify_boq.xlsx — do not hand-edit; regenerate.

'''

with open("demo_data.py", "w", encoding="utf8") as f:
    f.write(HEADER)
    f.write("SPECS = ")
    f.write(pprint.pformat(specs, width=96, sort_dicts=False))
    f.write("\n\n\n")
    f.write('''# ── The demo BOQ ────────────────────────────────────────────────────────────
# One complete Sify Bangalore schedule: 97 rows across three sections, with the
# area breakdown each section actually declares (External + L0 for A, T1 for B,
# none for C). Each line names the spec it came from and, for a family, which
# variant — so the seeded BOQ demonstrates the same spec -> line path a user
# takes through the picker.
#
# `s_pct` is stored as a PERCENTAGE (15.0), not a fraction: the workbook holds
# 0.15 in the escalation cell and the record's contract is percent.
#
# Rates are carried per line and are NOT re-derived from the spec defaults.
# Twelve lines in this schedule deliberately differ from base x (1 + escalation)
# — a tamper switch priced into the line at 2000/nos, a larger diameter at the
# Bangalore site — and the remark column says so. Recomputing them would erase
# real commercial decisions.

BOQ_META = ''')
    f.write(pprint.pformat({
        "id": str(uuid.uuid5(NS, "boq/sify-bangalore")),
        "ref": "SF/BOQ/26-27/0001",
        "fy": "26-27",
        "date": "2026-06-15",
        "rev_no": 0,
        "project_name": "Sify Bangalore",
        "site_location": "Bangalore, Karnataka",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "contact_person": "",
        "bill_gstin": "",
        "bill_city": "Bengaluru",
        "bill_state": "Karnataka",
        "rate_basis_label": "Mohali Rates",
        "payment_terms": "Material Payment 50% Advance & 50% After Delivery Or as per OEM Conditions.",
        "delivery_terms": "FOR Site",
        "notes": ("GST extra as applicable. Electricity, water & safe storage in client scope. "
                  "Scaffolding, JLG, lift, hydra, poklain and JCB not in our scope. "
                  "Labour payment 30% advance, 60% on running bill, 10% on completion."),
    }, width=96, sort_dicts=False))
    f.write("\n\nBOQ_SECTIONS = ")
    f.write(pprint.pformat(sections, width=96, sort_dicts=False))
    f.write("\n\nBOQ_LINES = ")
    f.write(pprint.pformat(lines, width=96, sort_dicts=False))
    f.write("\n")

print(f"specs={len(specs)} variants={sum(len(s['variants']) for s in specs)} lines={len(lines)}")
cats = {}
for s in specs:
    cats[s["category"]] = cats.get(s["category"], 0) + 1
print("categories:", cats)
print("\nTITLES:")
for s in specs:
    print(f"  [{s['category']:10}] {s['code']:36} {s['title']!r} ({len(s['variants'])}v)")
