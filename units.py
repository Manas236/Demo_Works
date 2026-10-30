"""
units.py — the unit of measure, and the GST UQC behind it.  A LEAF.
=================================================================
29 October 2026, CLIENT_CHANGES.md §0 **fifty-ninth** block, B3, from the
28 October 2026 meeting with Yogesh Bankar:

    every line-item form gets a dropdown — Nos (default), Mtrs, Kg, Set, Lot,
    Sq Ft, Sq M — with custom units addable at /settings. Each unit stores a
    display label and its GST UQC code (NOS, MTR, KGS, SET, SQF, SQM; Lot and
    any custom unit map to OTH). Existing free-text units stay as they are.

## Two things, and they are not the same thing

A **label** is what the client writes on a document: "Mtrs", "Sq Ft", "Lot".
A **UQC** is the three-letter code the GST portal accepts in GSTR-1 — `MTR`,
`SQF`, `OTH` — and there are only so many of them. The client's label and the
portal's code are different vocabularies, which is why a unit here is a pair
and not a string.

⚠ **NOTHING IN THIS APPLICATION FILES A RETURN, and no document prints a
  UQC today.** The code is stored so that the day a GSTR-1 export is built it
  does not have to guess — and so that a custom unit's answer is **recorded as
  `OTH` by decision** rather than invented later. ABOUT.md §7 gap 96 says what
  is still open.

## Existing free-text units stay as they are, and that is the load-bearing rule

Every unit already on a record was typed into a free-text box, and the
client's own sheets carry `Nos.`, `Mtrs.`, `Kgs.`, `Lump Sum`, `Job`, `Sq.Mtrs`
and `Ltrs` — none of which is one of the seven. **Not one of them is
rewritten.** `select_html()` keeps whatever a record carries as an extra,
selected option, so opening an old line and saving it changes nothing; and
`uqc_of()` answers `OTH` for a label it does not know rather than refusing.

The cleanup is a **tool**, `tools/clean_units.py`, idempotent and dry-run by
default, and **it has not been run** — the §0 block says so.

## Why a LEAF, and not `settings.py`

`series.py`'s constraint exactly: **`boq.py` may not import `settings.py`**
(`tests/test_import_directions.py` refuses the arrow, because `settings`
imports `quotation` and nothing downstream of it may import back), and the
BOQ's own line editor is the most important form this dropdown has to reach.
`charge.py`, `docsheet.py`, `boqpick.py`, `employee.py`, `project.py` and
`chrome.py` are refused the same arrow.

So this module imports **`pipeline` and `store` and nothing else of ours**,
and reads `STORE["settings"]` directly. That is the one-way trick this
repository already runs a dozen times: `settings.py` owns the *page* that
edits the record, this module owns the *rule* the record expresses, and
neither imports the other.

⚠ It may not import `branding.py` either — the completeness dot on the nav
  means *"a document will print an amber chip"*, and a unit list is not a
  statutory identity field.
"""

import pipeline as P
from store import STORE

# =============================================================================
# THE SEVEN, AND THEIR CODES
# =============================================================================
#
# The client's words on the left, the GST portal's code on the right — both
# from the 28 October ask, verbatim. **Nos is the default**, which is the one
# ordering decision in this list: it is first, and `DEFAULT_LABEL` names it so
# a form does not have to know that first means default.
DEFAULTS = (
    ("Nos",   "NOS"),
    ("Mtrs",  "MTR"),
    ("Kg",    "KGS"),
    ("Set",   "SET"),
    ("Lot",   "OTH"),    # ⚠ the portal has no "lot" — the ask says OTH
    ("Sq Ft", "SQF"),
    ("Sq M",  "SQM"),
)

DEFAULT_LABEL = DEFAULTS[0][0]

# What a unit the portal does not know is filed as. **A custom unit is always
# this**, by the client's own instruction, and so is `Lot`.
UQC_OTHER = "OTH"

LABEL_MAX = 24
UQC_MAX = 3

# Its own settings record, `series.py`'s and `charge_heads`' arrangement: a
# unit list is not a branding override and `branding.apply_settings()` must
# never push it onto a letterhead.
RECORD = "unit_list"
CUSTOM_KEY = "custom"


def custom() -> list:
    """
    The units an Owner added at `/settings`, as `[(label, uqc)]`.

    `[]` is the normal state and is byte-identical to having no record at all.
    """
    rec = (STORE.get("settings") or {}).get(RECORD) or {}
    out = []
    for row in rec.get(CUSTOM_KEY) or []:
        if isinstance(row, (list, tuple)) and row:
            label = str(row[0] or "").strip()[:LABEL_MAX]
            uqc = (str(row[1] if len(row) > 1 else "") or "").strip().upper()[:UQC_MAX]
        elif isinstance(row, dict):
            label = str(row.get("label") or "").strip()[:LABEL_MAX]
            uqc = str(row.get("uqc") or "").strip().upper()[:UQC_MAX]
        else:
            continue
        if label:
            out.append((label, uqc or UQC_OTHER))
    return out


def save_custom(rows: list) -> None:
    """Replace the custom list. `[]` clears it."""
    STORE.setdefault("settings", {})[RECORD] = {
        CUSTOM_KEY: [[str(a), str(b)] for a, b in rows]}


def pairs() -> list:
    """
    Every unit a form offers, `[(label, uqc)]` — **the seven, then the custom
    ones**, de-duplicated on the label with the first occurrence winning.

    ⚠ **A custom entry can never shadow one of the seven**, which is what
      stops somebody filing metres as `NOS` by typing "Mtrs" into the custom
      box. `/settings` refuses the duplicate as well; this is the second half,
      so the rule holds even against a row written straight into MySQL.
    """
    out, seen = [], set()
    for label, uqc in list(DEFAULTS) + custom():
        key = P.norm_name(label)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, uqc))
    return out


def labels() -> list:
    return [label for label, _u in pairs()]


def uqc_of(label) -> str:
    """
    The GST UQC for a label, or **`OTH`**.

    Matched on `pipeline.norm_name()` — casefolded and whitespace-collapsed —
    so "sq ft", "Sq Ft" and "SQ  FT" are one unit. **Nothing wider**: no
    prefix, no stemming, no "Mtrs." → "Mtrs". An unknown label is `OTH`,
    which is the honest answer for a unit nobody has mapped and is exactly
    what the client said a custom unit is.
    """
    key = P.norm_name(label)
    if not key:
        return ""
    for lab, uqc in pairs():
        if P.norm_name(lab) == key:
            return uqc or UQC_OTHER
    return UQC_OTHER


def is_known(label) -> bool:
    """Is this label one the dropdown offers? A legacy free-text unit is not."""
    key = P.norm_name(label)
    return bool(key) and any(P.norm_name(l) == key for l, _u in pairs())


# =============================================================================
# THE CONTROL
# =============================================================================

def options_html(current: str = "", blank: str = "") -> str:
    """
    The `<option>`s alone, for a caller that owns its own `<select>` tag.

    ⚠ **A value the list does not offer is kept as an extra, SELECTED option**
      — the whole of *"existing free-text units stay as they are"*. Opening a
      line that says `Lump Sum` and saving it writes `Lump Sum` back. The
      extra option is marked so a reader can see it is not one of the list's.
    """
    cur = str(current or "").strip()
    out = []
    if blank or not cur:
        out.append(f'<option value="">{P.esc(blank)}</option>')
    for label, _uqc in pairs():
        sel = " selected" if P.norm_name(label) == P.norm_name(cur) else ""
        out.append(f'<option value="{P.esc(label)}"{sel}>{P.esc(label)}</option>')
    if cur and not is_known(cur):
        out.append(f'<option value="{P.esc(cur)}" selected>'
                   f'{P.esc(cur)} &mdash; as written</option>')
    return "".join(out)


def select_html(name: str, current: str = "", *, aria: str = "Unit",
                blank: str = "", el_id: str = "", style: str = "",
                cls: str = "") -> str:
    """One unit dropdown. `name` is the posted field; everything else is dress."""
    bits = [f'name="{P.esc(name)}"']
    if el_id:
        bits.append(f'id="{P.esc(el_id)}"')
    if cls:
        bits.append(f'class="{P.esc(cls)}"')
    if style:
        bits.append(f'style="{P.esc(style)}"')
    bits.append(f'aria-label="{P.esc(aria)}"')
    return f'<select {" ".join(bits)}>{options_html(current, blank)}</select>'


def payload() -> list:
    """
    The list as a browser-side editor needs it — `[{"label": …, "uqc": …}]`.

    For `boq.py`'s line editor, which builds its rows in JavaScript and cannot
    call a Python renderer per row. ⚠ **The UQC travels with it even though
    the editor never shows it**, so the two halves cannot be read apart.
    """
    return [{"label": label, "uqc": uqc} for label, uqc in pairs()]
