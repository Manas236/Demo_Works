"""
pipeline.py — Deal Pipeline / Quotation Lifecycle
==================================================
Owns everything about *where a quotation stands commercially*: its sales
stage, the customer's incoming Purchase Order, and the won/lost outcome.

Why this is a separate module
-----------------------------
quotation.py is ~2,000 lines and is about *building the document*. This module
is about what happens to that document afterwards. Keeping them apart means
adding a stage, an editable field, or a filter is a one-line change here
instead of a hunt through template strings.

Import direction:  quotation.py → pipeline.py  (never the reverse),
so there is no circular import.

Direction note
--------------
The PO handled here is the one that arrives *from the customer*. A purchase
order always flows buyer → seller; on a quotation we are the seller, so we
record their PO, we never issue it. POs we issue to our own suppliers are a
separate pipeline and do not belong in this module.
"""

import html
from datetime import datetime

# =============================================================================
# STAGE VOCABULARY — single source of truth
# =============================================================================
# To add/rename/reorder a stage, edit this list only. Everything downstream
# (create form dropdown, edit panel, register filters, summary tiles) is
# generated from it.

STAGE_WON  = "Closed Won"
STAGE_LOST = "Closed Lost"

SALES_STAGES = [
    "Budgetary - Stage I",
    "Budgetary - Stage II",
    "Technical",
    "Commercial",
    "Negotiation",
    "PO Expected",
    STAGE_WON,
    STAGE_LOST,
]

DEFAULT_STAGE = "Budgetary - Stage II"

# A deal is "closed" once it reaches either terminal stage; everything else
# is still live and counts toward open pipeline value.
CLOSED_STAGES = (STAGE_WON, STAGE_LOST)
OPEN_STAGES   = [s for s in SALES_STAGES if s not in CLOSED_STAGES]

# Colour tone per stage — used for the badge. Anything unlisted renders neutral.
STAGE_TONE = {
    STAGE_WON:     "won",
    STAGE_LOST:    "lost",
    "PO Expected": "hot",
    "Negotiation": "warm",
}

# ── Policy switches ──────────────────────────────────────────────────────────
# Business rules we deliberately left adjustable rather than hardcoding.
#
# REQUIRE_PO_FOR_WON: when True, a quotation cannot be marked Closed Won
# without a customer PO number. Defaults False so the demo stays frictionless —
# flip it to True if the real process says "no PO, no win".
REQUIRE_PO_FOR_WON = False


# =============================================================================
# FIELDS THIS MODULE OWNS ON A QUOTATION RECORD
# =============================================================================
# name → default. ensure_fields() backfills these onto quotations that were
# created before this module existed, so nothing has to be migrated by hand.
PIPELINE_FIELDS = {
    "sales_stage":   DEFAULT_STAGE,
    "po_number":     "",
    "po_date":       "",
    "po_value":      0.0,
    "lost_reason":   "",
    "stage_history": None,   # None → fresh list per record (see ensure_fields)
}

# Free-text fields the update route is allowed to write, and their labels.
# Add a field here + to PIPELINE_FIELDS above and it becomes editable.
EDITABLE_TEXT_FIELDS = {
    "po_number":   "Customer PO No.",
    "po_date":     "PO Date",
    "lost_reason": "Reason",
}


def ensure_fields(q: dict) -> dict:
    """Backfill pipeline fields onto a quotation record. Idempotent."""
    for key, default in PIPELINE_FIELDS.items():
        if key not in q or q[key] is None:
            q[key] = [] if default is None else default
    if not q.get("sales_stage"):
        q["sales_stage"] = DEFAULT_STAGE
    return q


# =============================================================================
# PREDICATES
# =============================================================================

def stage_of(q: dict) -> str:
    return (q.get("sales_stage") or DEFAULT_STAGE).strip()

def is_won(q: dict)    -> bool: return stage_of(q) == STAGE_WON
def is_lost(q: dict)   -> bool: return stage_of(q) == STAGE_LOST
def is_closed(q: dict) -> bool: return stage_of(q) in CLOSED_STAGES
def is_open(q: dict)   -> bool: return not is_closed(q)

def stage_tone(stage: str) -> str:
    return STAGE_TONE.get((stage or "").strip(), "open")


# =============================================================================
# PARSING / FORMATTING
# =============================================================================

def parse_money(raw) -> float:
    """
    Lenient money parser — accepts '12,50,000', '₹ 1250000', '1250000.50', ''.
    Returns 0.0 on anything unparseable rather than raising, because a bad
    keystroke in a PO value should not lose the rest of the update.
    """
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = "".join(ch for ch in str(raw) if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned) if cleaned not in ("", "-", ".", "-.") else 0.0
    except ValueError:
        return 0.0


def fmt_money(v: float) -> str:
    """₹-less plain number with Indian-style grouping handled by the caller."""
    return f"{v:,.0f}"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def esc(v) -> str:
    """HTML-escape a value for safe interpolation into a template string."""
    return html.escape(str(v or ""))


_esc = esc  # internal shorthand used throughout this module


# =============================================================================
# UPDATE
# =============================================================================

def log_event(q: dict, note: str, stage_from: str = None, stage_to: str = None) -> dict:
    """
    Append a one-off entry to the audit trail without changing the stage.
    Used for "Quotation created."; also handy for any future system event.
    """
    ensure_fields(q)
    stage = stage_of(q)
    entry = {
        "at":   _now(),
        "from": stage_from if stage_from is not None else stage,
        "to":   stage_to   if stage_to   is not None else stage,
        "note": note,
        "po":   q.get("po_number", ""),
    }
    q["stage_history"].append(entry)
    return entry


def apply_update(q: dict, form) -> tuple[bool, str]:
    """
    Apply a pipeline update to a quotation record, in place.

    `form` is any mapping with .get() — a Flask request.form works directly.
    Only keys actually present in the form are touched, so a panel that posts
    just the stage will not blank out a previously recorded PO.

    Returns (ok, message). On failure the record is left untouched.
    """
    ensure_fields(q)

    old_stage = stage_of(q)
    new_stage = (form.get("sales_stage") or old_stage).strip()

    if new_stage not in SALES_STAGES:
        return False, f"Unknown sales stage: {new_stage!r}"

    # Stage the incoming values before committing, so validation failures
    # cannot leave the record half-updated.
    staged: dict = {}

    for field in EDITABLE_TEXT_FIELDS:
        if field in form:
            staged[field] = (form.get(field) or "").strip()

    if "po_value" in form:
        staged["po_value"] = parse_money(form.get("po_value"))

    po_number = staged.get("po_number", q.get("po_number", ""))

    if REQUIRE_PO_FOR_WON and new_stage == STAGE_WON and not po_number:
        return False, "Record the customer's PO number before marking this Closed Won."

    # ── Commit ───────────────────────────────────────────────────────────
    q.update(staged)
    q["sales_stage"] = new_stage

    note = (form.get("stage_note") or "").strip()
    if new_stage != old_stage or staged or note:
        q["stage_history"].append({
            "at":   _now(),
            "from": old_stage,
            "to":   new_stage,
            "note": note,
            "po":   po_number,
        })

    if new_stage != old_stage:
        return True, f"Stage updated: {old_stage} → {new_stage}"
    return True, "Deal details updated."


# =============================================================================
# FILTERING — register view
# =============================================================================
# Named groups shown as tabs. Each maps to a predicate over a quotation.
VIEWS = {
    "all":  ("All",     lambda q: True),
    "open": ("Open",    is_open),
    "won":  ("Won",     is_won),
    "lost": ("Lost",    is_lost),
}
DEFAULT_VIEW = "all"


def filter_quotations(quotations: dict, args) -> list[tuple[str, dict]]:
    """
    Filter the quotation store into a newest-first list of (id, record).

    Recognised query params (all optional, all combinable):
      view=all|open|won|lost   coarse outcome group
      stage=<exact stage>      single stage
      q=<text>                 substring match on ref / customer / PO number
    """
    view   = (args.get("view")  or DEFAULT_VIEW).strip().lower()
    stage  = (args.get("stage") or "").strip()
    search = (args.get("q")     or "").strip().lower()

    _, predicate = VIEWS.get(view, VIEWS[DEFAULT_VIEW])

    rows = []
    for qid, q in reversed(list(quotations.items())):
        ensure_fields(q)
        if not predicate(q):
            continue
        if stage and stage_of(q) != stage:
            continue
        if search:
            haystack = " ".join(str(q.get(k, "")) for k in
                                ("ref", "account_name", "to", "po_number", "buyer_ref")).lower()
            if search not in haystack:
                continue
        rows.append((qid, q))
    return rows


# =============================================================================
# SUMMARY — pipeline totals
# =============================================================================

def summarize(quotations: dict) -> dict:
    """
    Aggregate the whole store into counts and values.

    'value' is the quotation grand total. For won deals we also track
    po_value separately, because the PO the customer actually sends is often
    not the number we quoted — that gap is the useful figure.
    """
    out = {
        "by_stage": {s: {"count": 0, "value": 0.0} for s in SALES_STAGES},
        "open":  {"count": 0, "value": 0.0},
        "won":   {"count": 0, "value": 0.0, "po_value": 0.0},
        "lost":  {"count": 0, "value": 0.0},
        "total": {"count": 0, "value": 0.0},
        "win_rate": None,
    }

    for q in quotations.values():
        ensure_fields(q)
        stage = stage_of(q)
        value = float(q.get("grand_total") or 0.0)

        bucket = out["by_stage"].setdefault(stage, {"count": 0, "value": 0.0})
        bucket["count"] += 1
        bucket["value"] += value

        out["total"]["count"] += 1
        out["total"]["value"] += value

        if is_won(q):
            out["won"]["count"] += 1
            out["won"]["value"] += value
            out["won"]["po_value"] += float(q.get("po_value") or 0.0)
        elif is_lost(q):
            out["lost"]["count"] += 1
            out["lost"]["value"] += value
        else:
            out["open"]["count"] += 1
            out["open"]["value"] += value

    decided = out["won"]["count"] + out["lost"]["count"]
    if decided:
        out["win_rate"] = round(100.0 * out["won"]["count"] / decided)

    return out


# =============================================================================
# HTML FRAGMENTS
# =============================================================================

def stage_badge(stage: str) -> str:
    s = (stage or "").strip() or "—"
    return f'<span class="stage-badge tone-{stage_tone(s)}">{_esc(s)}</span>'


def po_cell(q: dict) -> str:
    """Compact PO display for the register — number over value, or a dash."""
    num = (q.get("po_number") or "").strip()
    val = float(q.get("po_value") or 0.0)
    if not num and not val:
        return '<span class="td-muted">—</span>'
    bits = []
    if num:
        bits.append(f'<span class="po-num">{_esc(num)}</span>')
    if val:
        bits.append(f'<span class="po-val">&#8377;&nbsp;{fmt_money(val)}</span>')
    return '<div class="po-cell">' + "".join(bits) + "</div>"


def history_html(q: dict) -> str:
    """Reverse-chronological audit trail. Empty string when nothing logged."""
    hist = q.get("stage_history") or []
    if not hist:
        return ""
    items = ""
    for h in reversed(hist):
        note = f'<div class="hist-note">{_esc(h.get("note"))}</div>' if h.get("note") else ""
        frm, to = h.get("from", ""), h.get("to", "")
        move = (f'{_esc(frm)} &rarr; <b>{_esc(to)}</b>' if frm != to
                else f'<b>{_esc(to)}</b> (details updated)')
        items += (f'<li><span class="hist-at">{_esc(h.get("at"))}</span>'
                  f'<span class="hist-move">{move}</span>{note}</li>')
    return f'<ul class="hist-list">{items}</ul>'


# =============================================================================
# STYLES — kept here so the module ships self-contained
# =============================================================================

PIPELINE_STYLES = """
<style>
  /* ── Stage badge ────────────────────────────────────────────────── */
  .stage-badge {
    display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.02em;
    padding:.22rem .6rem; border-radius:999px; white-space:nowrap;
    border:1px solid transparent;
  }
  .stage-badge.tone-open { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }
  .stage-badge.tone-warm { background:#fff7ed; color:#9a3412; border-color:#fed7aa; }
  .stage-badge.tone-hot  { background:#fefce8; color:#854d0e; border-color:#fde68a; }
  .stage-badge.tone-won  { background:#f0fdf4; color:#166534; border-color:#bbf7d0; }
  .stage-badge.tone-lost { background:#fef2f2; color:#991b1b; border-color:#fecaca; }

  /* ── Summary tiles ──────────────────────────────────────────────── */
  .pipe-tiles {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
    gap:.9rem; margin-bottom:1.3rem;
  }
  .pipe-tile {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); padding:.95rem 1.1rem; box-shadow:var(--shadow-sm);
  }
  .pipe-tile .pt-lbl {
    font-size:.68rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.08em; color:var(--muted); margin-bottom:.35rem;
  }
  .pipe-tile .pt-val { font-size:1.25rem; font-weight:700; letter-spacing:-.4px; }
  .pipe-tile .pt-sub { font-size:.73rem; color:var(--muted); margin-top:.15rem; }
  .pipe-tile.t-won  .pt-val { color:#166534; }
  .pipe-tile.t-lost .pt-val { color:#991b1b; }
  .pipe-tile.t-open .pt-val { color:var(--brand); }

  /* ── Filter bar ─────────────────────────────────────────────────── */
  .filter-bar {
    display:flex; align-items:center; gap:.55rem; flex-wrap:wrap;
    margin-bottom:1.1rem;
  }
  .filter-tabs { display:flex; gap:.3rem; flex-wrap:wrap; }
  .filter-tab {
    font-size:.78rem; font-weight:600; padding:.36rem .85rem; border-radius:999px;
    text-decoration:none; color:var(--muted); background:var(--surface);
    border:1px solid var(--border); transition:all .13s; white-space:nowrap;
  }
  .filter-tab:hover  { border-color:var(--brand); color:var(--brand); }
  .filter-tab.active { background:var(--brand); color:#fff; border-color:var(--brand); }
  .filter-bar form { display:flex; gap:.45rem; margin-left:auto; flex-wrap:wrap; }
  .filter-bar select, .filter-bar input[type="search"] {
    font-family:var(--font); font-size:.8rem; padding:.36rem .6rem;
    border:1px solid var(--border); border-radius:8px; background:var(--surface);
    color:var(--text);
  }
  .filter-bar .fb-clear { font-size:.76rem; color:var(--muted); text-decoration:none; align-self:center; }
  .filter-bar .fb-clear:hover { color:var(--brand); }

  .po-cell   { display:flex; flex-direction:column; gap:.1rem; }
  .po-num    { font-family:'SFMono-Regular',Consolas,monospace; font-size:.78rem; font-weight:700; }
  .po-val    { font-size:.72rem; color:var(--muted); }

  /* ── Deal panel (quotation view page) ───────────────────────────── */
  .deal-panel {
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius); box-shadow:var(--shadow-sm);
    padding:1.2rem 1.4rem; margin-bottom:1.4rem;
  }
  .deal-head {
    display:flex; align-items:center; justify-content:space-between;
    gap:1rem; flex-wrap:wrap; margin-bottom:1rem;
    padding-bottom:.75rem; border-bottom:1px solid var(--border);
  }
  .deal-head .dh-title {
    font-size:.73rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.09em; color:var(--brand);
  }
  .deal-quick { display:flex; gap:.4rem; flex-wrap:wrap; }
  .deal-quick button {
    font-family:var(--font); font-size:.76rem; font-weight:700; cursor:pointer;
    padding:.34rem .8rem; border-radius:8px; border:1px solid var(--border);
    background:var(--bg); color:var(--text); transition:all .13s;
  }
  .deal-quick button:hover { transform:translateY(-1px); }
  .deal-quick .qa-won  { background:#f0fdf4; color:#166534; border-color:#bbf7d0; }
  .deal-quick .qa-lost { background:#fef2f2; color:#991b1b; border-color:#fecaca; }

  .deal-grid {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(165px,1fr));
    gap:.85rem; align-items:end;
  }
  .deal-grid .form-group { display:flex; flex-direction:column; gap:.3rem; }
  .deal-grid label {
    font-size:.7rem; font-weight:700; text-transform:uppercase;
    letter-spacing:.07em; color:var(--muted);
  }
  .deal-grid input, .deal-grid select {
    font-family:var(--font); font-size:.85rem; padding:.5rem .65rem;
    border:1px solid var(--border); border-radius:8px;
    background:var(--bg); color:var(--text); width:100%;
  }
  .deal-grid input:focus, .deal-grid select:focus {
    outline:none; border-color:var(--brand); background:var(--surface);
  }
  .deal-actions { display:flex; align-items:center; gap:.7rem; margin-top:1rem; flex-wrap:wrap; }
  .deal-variance { font-size:.78rem; color:var(--muted); }
  .deal-variance b.up   { color:#166534; }
  .deal-variance b.down { color:#991b1b; }

  /* ── History ────────────────────────────────────────────────────── */
  .hist-list { list-style:none; margin-top:1rem; padding-top:.85rem; border-top:1px solid var(--border); }
  .hist-list li { display:flex; flex-wrap:wrap; gap:.55rem; font-size:.78rem; padding:.3rem 0; }
  .hist-at   { color:var(--muted); font-family:'SFMono-Regular',Consolas,monospace; font-size:.72rem; min-width:8.5rem; }
  .hist-move { color:var(--text); }
  .hist-note { width:100%; padding-left:9rem; color:var(--muted); font-style:italic; }

  @media (max-width:640px) {
    .filter-bar form { margin-left:0; width:100%; }
    .hist-note { padding-left:0; }
  }
</style>
"""
