# Fixtures — the client workbooks

Two real client spreadsheets are used by this project. **Neither is committed,
and neither should be.** They are a customer's priced schedule and their
running-account position: commercial data that does not belong in a git history
that may be cloned, forked or handed to a contractor.

Both are listed in `.gitignore`.

## What to place here

| File | What it is | Needed by |
|---|---|---|
| `sify_boq.xlsx` | The Sify Bangalore BOQ — 3 sections, 97 lines, supply and installation priced separately. | `tools/gen_demo_data.py`; the Phase 3 importer and its tests. |
| `annexure.xlsx` | The same schedule extended with nine RA claims and their running balances. | The Phase 3 RA replay tests. |

Place them **either** in this directory **or** in the repository root — the
tests look in both, so an existing checkout keeps working:

```
Demo_Works/
├── fixtures/
│   ├── README.md          <- this file
│   ├── sify_boq.xlsx      <- put them here
│   └── annexure.xlsx
└── sify_boq.xlsx          <- or here; either is found
```

## What happens without them

Nothing breaks.

- **The app runs normally.** The workbooks are *never* read at runtime. The
  seeded specification library and the demo BOQ live in `demo_data.py`, which
  was generated from `sify_boq.xlsx` once and is committed.
- **The test suite passes.** Tests that need a workbook **skip with an explicit
  message** naming the missing file and pointing here. They do not fail, and
  they do not silently pass either.

```
SKIPPED [1] fixtures/conftest.py:34: fixture workbook 'sify_boq.xlsx' not found
           - see fixtures/README.md
```

## Regenerating the demo data

Only needed if the source workbook changes:

```bash
python tools/gen_demo_data.py      # reads sify_boq.xlsx, rewrites demo_data.py
```

It is byte-for-byte reproducible. Clause text, rates, quantities and variant
sets are read mechanically; only each spec's short title, code and category are
a human judgement, and those live in `tools/curation.py`.

## ⚠ A note on what is already committed

`demo_data.py` contains this client's **actual negotiated rates** for the Sify
Bangalore project — they were extracted from `sify_boq.xlsx` to seed the
library. Keeping the workbooks out of git does not undo that. If the rates
themselves are considered confidential, `demo_data.py` needs to be regenerated
against a scrubbed or synthetic source, and the git history rewritten. That is
a decision for the project owner, recorded here so it is not forgotten.
