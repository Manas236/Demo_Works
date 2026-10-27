"""
docnum.py — the MANUAL document number, forward only
=====================================================

CLIENT_CHANGES.md §0's **fifty-fourth** block (27 October 2026, the call with
Yogesh Bankar) is the authorisation. The client keeps a paper book; a document
raised here has to be able to carry the number that book has already reached,
and then carry on from it.

## The rule, in one line

    accepted  ⟺  entered > the highest ordinal EVER used in this scope
                 (or entered == the prefilled default, always allowed)

and on save the series advances to **entered + 1**, so a skipped number is
never handed out later.

## What "EVER used" means, and why a scan is not enough

A `max+1` scan over the surviving records answers *"what is the highest number
still in the store"*. That is a different question, and the difference is
exactly a deleted document: delete `PI-0050` and the scan drops back to 49,
which would let somebody type 50 a second time onto a different document. The
paper carrying the first 50 has already left the building.

So this module keeps a **high-water ledger** beside the scan —
`STORE["settings"]["document_number_highwater"]`, shaped
`{kind: {scope: int}}` — raised by `note_used()` on **every** save of one of
these four documents, automatic or typed. `highest_used()` is the max of the
two, so:

  * a **cancelled** document counts because it is still in the collection and
    the scan sees it (nothing here filters on status — that is deliberate, and
    `tests/test_docnum.py` mutates the filter back in to prove it);
  * a **deleted** document counts because the ledger outlived it.

⚠ **The ledger does NOT feed the automatic minter, and that is on purpose.**
  `series.next_seq()` is untouched and every automatic number is byte-identical
  to what it was before this module existed — which is why no print golden and
  no register golden moved. The ledger is read by the *override* validator and
  by nothing else. The consequence is stated rather than smoothed over:
  deleting a PI or a PO still lets the AUTOMATIC series re-issue that ordinal,
  exactly as it did before 27 October 2026. ABOUT.md §7 **gap 83**.

## The tax invoice is the one that scans four places at once

Rule 46(b)'s uniqueness is **per supplier GSTIN per financial year**, and this
application prints a tax invoice from four places:

  * `invoice.py`'s ordinary TI, raised from a proforma  — `invoices.ref`
  * a TI raised from a BOQ                              — `invoices.ref`
    (the same collection: `invoice.from_boq()` writes a `purchases`-shaped
    record into `STORE["invoices"]` like any other TI — there is no second
    collection to scan, and that is worth saying because the brief names it
    as a separate source)
  * a single-leg RA bill's statutory serial             — `ra_bills.tax_invoice_ref`
  * a merged RA's statutory serial                      — `merged_ras.tax_invoice_ref`

⚠ **THIS IS WHY THIS MODULE IS A LEAF, and it is the same argument
  `docsheet.py` and `series.py` already make.** `ra.py` may never import
  `invoice.py`. A cross-collection check written inside either one would
  satisfy that prohibition on paper and defeat it in practice, because the
  coupling would run through the basement. This module imports `store` and
  `pipeline` and **nothing else from the app**, and reads the three
  collections directly — the one-way trick used between quotation/proforma,
  boq/ra, ra/receipt and boq/challan. `tests/test_import_directions.py` pins
  it.

⚠ **The union is taken on the ORDINAL, across series codes.** `SF/RI/26-27/0007`
  and `SF/TI/26-27/0007` both contribute **7** to the tax invoice's
  highest-used figure. That is stricter than the three-series design
  (`TI` / `MI` / `RI` were measured on 25 September 2026 and cannot collide
  when minted automatically) and it is deliberate: this is the one path where
  a **human types a statutory serial**, which is precisely the case the three
  series do not protect — ABOUT.md §7 **gap 32**, whose live record is an RA
  bill carrying a typed `SF/TI/26-27/0007`. Refusing a few ordinals a stricter
  reading would have allowed costs an operator one retry; allowing a duplicate
  statutory serial costs them a GSTR-1 correction. ⚠ **It does NOT close gap
  32**, which is about a value already in the live database and about the
  *automatic* minters; see that entry and gap 83.

⚠ **Which financial year a stored string belongs to is read from the STRING
  first.** `SF/TI/26-27/0007` typed onto an RA bill whose own `fy` is `27-28`
  is a `26-27` number — that is `series.py`'s `SERIES_PREFIX` lesson, in the
  one place it matters most, and the record's `fy` key is only the fallback
  for a string that carries no year at all.

## What is NOT here

⚠ **The DRAFT PO.** `po_draft.py` is being edited by an unpushed office-PC
  pass and touching it here guarantees a conflict in the one file that pass is
  about — §0's fifty-fourth block records the decision. Its stored high-water
  counter is untouched.

⚠ **`ra.next_ra_no()`** is the per-project RA sequence, reset per BOQ by
  design — `series.py` refuses it a floor for the same reason and so does
  this. **The measurement sheet, the work order and the quotation** are out
  too; `quotation.py` is frozen and its series deliberately carries no floor.

⚠ **No lock, and nothing here adds one.** The minters are still unguarded
  scan-max-then-plus-one, which is why `gunicorn` runs `--workers 1
  --threads 1` (DEPLOY.md §8.2). Two threads can still read the same max.
  A typed number makes that neither more nor less likely.

⚠ **It asks no permission question.** `auth.py` sits at the bottom of the
  graph and a leaf that imported it would acquire a reason to grow; the four
  document modules each pass `may_override` in, from their own function-body
  `import auth` — the hatch `boq.py`, `invoice.py`, `proforma.py`,
  `measurement.py` and `address.py` already use for `can_reach()`.
"""

import datetime

import pipeline as P
from store import STORE

# The ledger. Its own settings key, exactly as `document_series_floors`,
# `po_draft_series` and `delivery_challan_series` are — so
# `branding.apply_settings()` never pushes it onto the letterhead and the
# nav's amber completeness dot never counts it as a missing statutory detail.
HIGHWATER_RECORD = "document_number_highwater"

# The delivery challan's series record, read directly rather than through
# `settings.py`: this module may not import it (settings imports quotation;
# nothing downstream of it may import back), and `series.py` reads
# `STORE["settings"]` the same way for the same reason.
DC_SERIES_RECORD = "delivery_challan_series"

# The scope key a series with no financial year files its one figure under.
# A string, because this record is persisted as JSON.
GLOBAL_SCOPE = "*"

# ── the four kinds ─────────────────────────────────────────────────────────
TI = "TI"   # tax invoice — from a proforma AND from a BOQ
PI = "PI"   # proforma invoice
PO = "PO"   # purchase order (we are the buyer)
DC = "DC"   # delivery challan

# Every place a TAX INVOICE number can be in the store. See the header.
TI_SOURCES = (
    ("invoices",   "ref"),
    ("ra_bills",   "tax_invoice_ref"),
    ("merged_ras", "tax_invoice_ref"),
)

# `{kind: (label, fy_scoped, [(collection, field), …])}`.
#
# ⚠ `fy_scoped` is the same question `series.Series.scope_for()` asks, and the
#   answers agree with it by inspection rather than by import: TI and PO reset
#   each April, PI is one running series, and the challan's counter has never
#   had a year in it.
KINDS = {
    TI: ("Tax invoice", True,  TI_SOURCES),
    PI: ("Proforma invoice", False, (("proformas", "ref"),)),
    PO: ("Purchase order", True,  (("purchases", "ref"),)),
    DC: ("Delivery challan", False, (("delivery_challans", "ref"),)),
}


# ── reading a stored number ────────────────────────────────────────────────

def ordinal_of(raw) -> int:
    """
    The numeric tail of a stored document number, or 0 when there is none.

    `SF/TI/26-27/0007` → 7 · `PI-0007` → 7 · `54` → 54 · `` → 0.

    Both separators are tried because the four series genuinely use both:
    the FY-scoped ones split on `/`, the proforma on `-`, and the challan with
    a blank prefix is a bare integer with no separator at all. A tail that is
    not all digits contributes nothing rather than raising — a hand-edited
    record must not be able to 500 a form.
    """
    text = str(raw or "").strip()
    if not text:
        return 0
    tail = text.rpartition("/")[2]
    tail = tail.rpartition("-")[2]
    return int(tail) if tail.isdigit() else 0


def fy_of_ref(raw, fallback: str = "") -> str:
    """
    The financial year a stored number belongs to — **from the string first**.

    `SF/TI/26-27/0007` → `26-27`, whatever the record it sits on says its own
    `fy` is. That is the whole of `series.py`'s `SERIES_PREFIX` lesson, and it
    matters most here: the live record ABOUT.md §7 gap 32 reports is a
    `tax_invoice_ref` typed onto a bill from a different series.

    A string carrying no year segment falls back to the record's `fy` key.
    """
    for part in str(raw or "").split("/"):
        bit = part.strip()
        if (len(bit) == 5 and bit[2] == "-"
                and bit[:2].isdigit() and bit[3:].isdigit()):
            return bit
    return str(fallback or "")


def scope_for(kind: str, fy: str) -> str:
    """The numbering scope a date falls in — the FY, or the whole series."""
    _label, fy_scoped, _sources = KINDS[kind]
    return str(fy or "") if fy_scoped else GLOBAL_SCOPE


# ── the high-water ledger ──────────────────────────────────────────────────

def highwater() -> dict:
    """
    The whole ledger, `{kind: {scope: int}}`, as a clean copy.

    `{}` when nothing has ever been saved, which is what a fresh database
    looks like. Junk values are dropped rather than raising, `series.floors()`'
    contract.
    """
    saved = (STORE.get("settings") or {}).get(HIGHWATER_RECORD) or {}
    out = {}
    for kind, scopes in saved.items():
        if kind not in KINDS or not isinstance(scopes, dict):
            continue
        clean = {}
        for scope, value in scopes.items():
            try:
                n = int(value)
            except (TypeError, ValueError):
                continue
            if n > 0:
                clean[str(scope)] = n
        if clean:
            out[kind] = clean
    return out


def note_used(kind: str, fy: str, n) -> None:
    """
    Raise the ledger to `n`. **Called on EVERY save, automatic or typed.**

    Only ever raises: an out-of-order call with a lower figure leaves the
    ledger where it is, because the question it answers is "what is the
    highest number that has ever existed", and that cannot go down.
    """
    try:
        value = int(n)
    except (TypeError, ValueError):
        return
    if value <= 0:
        return

    scope = scope_for(kind, fy)
    settings = STORE.setdefault("settings", {})
    record = dict(settings.get(HIGHWATER_RECORD) or {})
    scopes = dict(record.get(kind) or {})
    if value > int(scopes.get(scope, 0) or 0):
        scopes[scope] = value
        record[kind] = scopes
        settings[HIGHWATER_RECORD] = record


# ── the scan ───────────────────────────────────────────────────────────────

def scanned_max(kind: str, fy: str) -> int:
    """
    The highest ordinal still in the store for this kind, in this scope.

    ⚠ **Nothing here filters on status.** A CANCELLED tax invoice is still in
      `STORE["invoices"]` and its number is still spent — a GST series has to
      stay consecutive and the document prints marked CANCELLED rather than
      vanishing. Adding a status filter would hand its serial out a second
      time, which is why `tests/test_docnum.py` mutates one in to prove this
      line is load-bearing.
    """
    _label, fy_scoped, sources = KINDS[kind]
    want = scope_for(kind, fy)
    highest = 0
    for collection, field in sources:
        for rec in (STORE.get(collection) or {}).values():
            raw = rec.get(field)
            if not str(raw or "").strip():
                continue
            if fy_scoped and fy_of_ref(raw, rec.get("fy")) != want:
                continue
            highest = max(highest, ordinal_of(raw))
    return highest


def stored_counter(kind: str) -> int:
    """
    The highest ordinal a STORED counter says has been spent, or 0.

    Only the delivery challan has one: its series is a high-water counter at
    `/settings` rather than a `max+1` scan, and `challan.next_ref()`'s own
    comment is explicit that deleting a challan **spends** its number. So the
    counter already encodes "highest ever used + 1" and is read as such —
    `next_no` of 55 means 54 has gone out. The other three have no counter and
    answer 0.
    """
    if kind != DC:
        return 0
    saved = (STORE.get("settings") or {}).get(DC_SERIES_RECORD) or {}
    try:
        nxt = int(str(saved.get("next_no") or "1").strip() or "1")
    except (TypeError, ValueError):
        nxt = 1
    return max(nxt - 1, 0)


def highest_used(kind: str, fy: str) -> int:
    """
    The highest ordinal EVER used in this scope — the figure a typed number
    has to beat. 0 when the series has never been used.

    Three readings, and the answer is the largest:

      * the **scan** over the surviving records (cancelled ones included);
      * the **stored counter**, for the challan, which is already a high-water
        mark;
      * the **ledger**, which is the only one of the three that outlives a
        deleted document.
    """
    return max(scanned_max(kind, fy), stored_counter(kind),
               int(highwater().get(kind, {}).get(scope_for(kind, fy), 0) or 0))


# ── the rule ───────────────────────────────────────────────────────────────

def validate(kind: str, fy: str, typed, default_n: int,
             may_override: bool) -> tuple:
    """
    `(ordinal, error)` for a typed number. **Always returns an ordinal**, so a
    refused form can re-render carrying what the operator typed —
    `address._validate()`'s contract, which every form in this app holds to.

    The order of the checks is the order the operator meets them:

      1. **Blank, or the prefilled default** — accepted, always, and without
         consulting the permission. Somebody who may not type a number still
         has to be able to save the document, and the default is what the
         series was going to issue anyway.
      2. **Not digits** — refused by shape before anything is scanned.
      3. **Changed, without the permission** — refused. This is the server
         half of the gate; the field is also rendered read-only, and a
         read-only field is a hint rather than a rule.
      4. **At or below the highest ever used** — refused, NAMING that figure,
         because an error that says only "invalid" costs somebody an afternoon
         (INTRODUCTION.md §2).

    ⚠ **`default_n` is accepted even when it is at or below the highest ever
      used**, and that case is reachable: the automatic minters scan one
      collection each, and the tax invoice's `highest_used()` scans four. A
      store whose highest RA `tax_invoice_ref` is 0007 while `invoices` holds
      only 0001 prefills `0002` and reports a highest of 7. Refusing the
      prefill would make the form unusable for a number nobody typed, so the
      default passes and the operator is told. ABOUT.md §7 **gap 83**.
    """
    text = str(typed if typed is not None else "").strip()
    try:
        default_n = int(default_n)
    except (TypeError, ValueError):
        default_n = 0

    if not text:
        return default_n, ""
    if not text.isdigit():
        return default_n, (
            f"{KINDS[kind][0]} number: digits only — type the numeric part "
            f"and nothing else.")

    entered = int(text)
    if entered == default_n:
        return entered, ""

    if not may_override:
        return default_n, (
            f"{KINDS[kind][0]} number: you do not have permission to set a "
            f"document number by hand, so it stays at {default_n:04d}.")

    highest = highest_used(kind, fy)
    if entered <= highest:
        return entered, (
            f"{KINDS[kind][0]} number {entered:04d} is not available — the "
            f"highest already used in this series is {highest:04d}. "
            f"A number only ever goes forward, so type {highest + 1:04d} or "
            f"more.")
    return entered, ""


# ── the override trail ─────────────────────────────────────────────────────

def override_entry(was: str, now: str, actor_id: str) -> dict:
    """
    The record of one typed number — **stored on the document, never printed**.

    `actor_id` is the user's **id**, not their display name: a display name is
    re-attributable (ABOUT.md §7 gap 41) and the point of this entry is to say
    who, unambiguously, a year later.
    """
    return {
        "from": str(was or ""),
        "to":   str(now or ""),
        "by":   str(actor_id or ""),
        "at":   datetime.datetime.now().replace(microsecond=0).isoformat(" "),
    }


def record_override(rec: dict, was: str, now: str, actor_id: str) -> None:
    """Attach the trail to a document, and only when the number actually moved."""
    if str(was or "") == str(now or ""):
        return
    rec["number_override"] = override_entry(was, now, actor_id)


# ── the one control all four forms render ──────────────────────────────────
#
# One widget rather than four, for `docsheet.py`'s reason: four copies of a
# field is four chances for the read-only half to drift from the validated
# half.

NUMBER_STYLES = """
<style>
  .dnum-row { display:flex; align-items:center; gap:.35rem; flex-wrap:wrap; }
  .dnum-fixed { font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
                font-size:.95rem; color:var(--muted); white-space:nowrap; }
  .dnum-row input.dnum-seq { width:7.5rem; font-family:ui-monospace,
                SFMono-Regular,Menlo,monospace; text-align:right; }
  .dnum-note { color:var(--muted); font-size:.82rem; margin-top:.3rem; }
  .dnum-warn { display:none; margin-top:.35rem; font-size:.82rem;
               color:#9a6700; background:#fff8e5; border:1px solid #f2d994;
               border-radius:4px; padding:.35rem .55rem; }
</style>
"""


def split_ref(ref: str) -> tuple:
    """
    `(fixed, tail)` — the part nobody may type, and the part they may.

    `SF/TI/26-27/0001` → `("SF/TI/26-27/", "0001")`
    `PI-0001`          → `("PI-", "0001")`
    `54`               → `("", "54")`   ← the challan with a blank prefix

    The split is on the LAST separator, so a prefix containing one survives.
    """
    text = str(ref or "")
    for sep in ("/", "-"):
        head, found, tail = text.rpartition(sep)
        if found and tail.isdigit():
            return head + found, tail
    return ("", text) if text.isdigit() else (text, "")


def number_field(kind: str, ref: str, *, may_override: bool,
                 typed: str = "", field: str = "doc_no_seq",
                 skip_note: bool = False) -> str:
    """
    The prefilled, part-editable number control.

    **The prefix and the financial year are rendered as text, not as a
    disabled input**, which is what makes them unpostable rather than merely
    unclickable: a disabled input can be re-enabled in a browser's inspector
    in four seconds, and the server would then have a value it was told not to
    trust. Only the tail is posted, and `validate()` is what accepts it.

    `may_override=False` renders the tail read-only AND the server refuses a
    changed value — the two halves of point 8, neither of them sufficient
    alone.

    `skip_note=True` adds the tax invoice's own one-line warning. It is
    **non-blocking and never printed**: it lives on the form, it is shown by
    the browser when the typed value runs ahead of the prefill, and nothing
    about it reaches the document or a golden.
    """
    fixed, tail = split_ref(ref)
    value = str(typed or "").strip() or tail
    ro = "" if may_override else " readonly"
    hint = ("Only the numbered part can be changed, and only forward."
            if may_override else
            "Set automatically. Changing it needs the "
            "&ldquo;set a document number by hand&rdquo; permission.")

    warn = ""
    if skip_note and may_override:
        # ⚠ Doubled braces: this whole module's HTML is f-string territory and
        #   a single brace here closes the expression (CLAUDE.md).
        warn = f"""
  <div class="dnum-warn" id="{P.esc(field)}_warn">A number ahead of
    {P.esc(tail)} leaves the ones in between unused. They will show as a gap
    in the <b>documents issued</b> table of your GSTR&#8209;1.</div>
  <script>
  (function () {{
    var box  = document.getElementById({P.json_for_script(field)});
    var warn = document.getElementById({P.json_for_script(field + "_warn")});
    var base = parseInt({P.json_for_script(tail or "0")}, 10);
    if (!box || !warn) {{ return; }}
    function sync() {{
      var n = parseInt(box.value, 10);
      warn.style.display = (!isNaN(n) && !isNaN(base) && n > base) ? "block" : "none";
    }}
    box.addEventListener("input", sync);
    sync();
  }})();
  </script>"""

    return f"""
  <div class="dnum-row">
    {f'<span class="dnum-fixed">{P.esc(fixed)}</span>' if fixed else ''}
    <input type="text" id="{P.esc(field)}" name="{P.esc(field)}"
           class="dnum-seq" value="{P.esc(value)}" inputmode="numeric"
           autocomplete="off"{ro}/>
  </div>
  <div class="dnum-note">{hint}</div>{warn}"""
