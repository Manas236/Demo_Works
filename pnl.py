"""
pnl.py — the project profit and loss  (CLIENT_CHANGES-2.md **C6**)
====================================================================
No routes, and no HTML but the one sentence under the `/projects` register.
**Every figure here is DERIVED when it is asked for, and NOTHING is stored** —
not on a project, not on a BOQ, not on any document. The panel that shows it is
`projectview._pnl_panel()`; this module computes, that one renders.

What C6 is
----------
CC-2's C6, in full:

    Planned margin from the BOQ against actual cost from purchase orders and
    recorded charges, with the difference shown.

    **Double-count trap:** attendance-based wages and the installation base
    rate both represent labour. Subtracting both counts labour twice. Decide
    which is authoritative before wiring C5 into C6.

**The trap is answered, not worked around.** Manas, 7 October 2026: *the
installation base rate does NOT include labour — labour is separate.* So site
labour is a cost row of its own and subtracting it does not count labour twice.
That answer closes CC-2's Open question 4, and CLIENT_CHANGES.md §0's
**forty-seventh** block records it — the authority for everything here,
including what goes beyond C6's two sentences (billed revenue, work orders,
site labour, the cash section and the untagged-cost line), each named there.

Three sections, and they never mix
----------------------------------
    PLANNED   each TIP revision's lines              tax-EXCLUSIVE
    TO DATE   what was billed, what was spent        tax-EXCLUSIVE
    CASH      billed incl. GST, received, owed       tax-INCLUSIVE

⚠ ABOUT.md §7 gap 31 was a tax-exclusive figure set beside a tax-inclusive one
  on one screen. Each section here reads EITHER the documents' taxable figures
  OR their GST-inclusive ones, never both, and the cash section is the one
  labelled as including GST.

The rules — each a judgement, recorded where it is applied
----------------------------------------------------------
* **Planned.** The BASE rate is what an item COSTS Samruddhi; the net rate
  (`boq.net_rate()`) is what it SELLS at. Read from the LATEST revision of each
  revision chain on the project (`ra.latest_revision()`), never snapshotted. A
  line with a blank quantity, or with no rate on either track, is SKIPPED and
  COUNTED (`boq.lines_without_qty()`, `boq.lines_not_priced()`) — never read as
  0. A priced line with no base rate has its cost NOT RECORDED
  (`boq.lines_without_cost()`): the panel says so beside the margin, because a
  low estimate made of missing base rates must never read as a good margin.
* **Billed.** ISSUED RA bills only (`ra.status_of()` — draft and cancelled are
  out; an unrecognised status reads as issued, `ra.py`'s own safe default),
  each at its own STORED `claim_subtotal`, the figure its tax was computed on —
  never re-read from the BOQ. A merged RA holds no claims and carries the SUM of
  its two legs' stored totals (CC-2 C3), so it is never added: its legs are
  already counted, once each. Tax invoices reach a project through their
  proforma's `project_id` (the inheritance `/projects/view` already draws),
  non-cancelled, at `subtotal`. ⚠ **A tax invoice whose number is an issued RA
  bill's `tax_invoice_ref` is the SAME billing** — a serial typed onto the bill
  before the RI series existed — and is counted ONCE, as the RA bill.
* **Actual cost — one row per source, never blended.** Purchase orders in a
  COMMITTED status (`COMMITTED_PO_STATUSES`) at `taxable_value`, with any charge
  outside the tax base on a row of its own; ISSUED work orders at their pre-tax
  total (`workorder.totals_of()["grand"]`, ABOUT.md §7 gap 55 — its own row);
  charges at `taxable_amount`; site labour priced by
  `attendance.labour_cost_of()`. A draft purchase order from `po_draft.py` is
  an INTENT — it carries no rate — and is never a cost.
* **Rounding.** A line's product is the BOQ's own (`boq.amount_of()`,
  unrounded, exactly as the BOQ stores its amounts); every TOTAL is rounded
  ONCE to the paisa, half up (`boq.round_half_up()`, Excel's ROUND), and every
  difference is taken between two rounded totals, so a figure on the panel is
  always exactly the difference of the two figures beside it. Stored document
  figures are read as stored.
* **Untagged.** Cost tagged to no LIVE project — a blank `project_id`, or one
  naming a project that no longer exists — is summed for the register's line,
  never spread across the projects that were tagged (ABOUT.md §7 gap B5).

Import direction
----------------
    pnl.py ──► boq.py         net_rate, amount_of, round_half_up, typed_num and
                              the three line counts
    pnl.py ──► ra.py          latest_revision, status_of and the receipts
                              arithmetic (received / written off / outstanding)
    pnl.py ──► merged_ra.py   live_merge_of() — for the NOTE, never the money
    pnl.py ──► purchase.py    PO_STATUSES, DEFAULT_STATUS, charges_of, charge_totals
    pnl.py ──► workorder.py   status_of, totals_of
    pnl.py ──► attendance.py  markings_for_project, markings_on_no_project,
                              labour_cost_of — and NEVER cost_of()
    pnl.py ──► quotation.py   _inr, for the register's one sentence
    pnl.py ──► store

⚠ Only `projectview.py` (the panel) and `project.py` (the register's line)
  import this module — and `project.py` only INSIDE a function, because it is
  held to a leaf: a module-level arrow from there would hang the whole document
  chain under the project entity.
⚠ It reads `STORE["projects"]`, `["proformas"]`, `["invoices"]`,
  `["purchases"]`, `["purchase_orders"]`, `["work_orders"]` and `["charges"]`
  directly and imports none of `project.py`, `proforma.py`, `invoice.py`,
  `po_draft.py` or `charge.py` — the one-way trick, again.
⚠ It never imports `auth.py`: who may see a figure is decided per view by the
  page that renders it (ABOUT.md §7 gap 24), never by the arithmetic.
"""

import math

import attendance as AT
import boq as BQ
import merged_ra as MRA
import purchase as PU
import ra as RA
import workorder as WO
from quotation import _inr
from store import STORE

TRACKS = ("supply", "install")

# ⚠ **Which purchase-order statuses are a COST.** `purchase.py`'s lifecycle is
#   Draft → Issued → Acknowledged → Partially Received → Received, or Cancelled.
#   A Draft is "written, not yet sent to the vendor" (`PO_STATUSES`' own words)
#   — nothing is committed — and a Cancelled order is "withdrawn". Everything
#   from Issued on is a commitment the vendor has been told about. Derived from
#   `PO_STATUSES` rather than restated, so a status added there is counted the
#   day it exists — and a status this module has never heard of is counted as
#   UNRECOGNISED, not as a cost.
#   ⚠ `purchase.job_cost()` counts a Draft as committed; this deliberately does
#   not, because a P&L's actual cost is money the vendor has been promised.
NOT_COMMITTED_PO_STATUSES = ("Draft", "Cancelled")
COMMITTED_PO_STATUSES = tuple(s for s in PU.PO_STATUSES
                              if s not in NOT_COMMITTED_PO_STATUSES)


# =============================================================================
# HELPERS
# =============================================================================

def _paise(x):
    """A total, rounded once to the paisa, half up — or None for no figure."""
    return None if x is None else BQ.round_half_up(x, 2)


def _stored(v):
    """
    A figure STORED on a document, as a float — or `None` when there is none.

    ⚠ **None, never 0.0, for a missing figure.** A record with no total has
    nothing to say, and a 0 would be a statement it never made — exactly
    `projectview._total_of()`'s rule. Text, a bool and a non-finite number are
    no figure either.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _line_figure(v):
    """A BOQ line's quantity or base rate, read by the BOQ's own reader
    (`boq.typed_num()`): blank and the client's "-" are `None`, a number is
    itself, anything else is `None` too — never 0."""
    value, bad = BQ.typed_num(v)
    return None if bad else value


def _serial(ref) -> str:
    """A document number compared as a number is compared on paper: case and
    spacing ignored, nothing else. `""` for no number at all."""
    return " ".join(str(ref or "").split()).upper()


def _pid(rec) -> str:
    return str((rec or {}).get("project_id") or "").strip()


def _project_boq_ids(project_id: str) -> set:
    """Every BOQ id filed under this project — every revision, because an RA
    bill is raised against a SPECIFIC revision. A blank id matches nothing."""
    pid = str(project_id or "").strip()
    if not pid:
        return set()
    return {str(bid) for bid, b in (STORE.get("boqs") or {}).items()
            if _pid(b) == pid}


# =============================================================================
# PLANNED — from the TIP revision of each schedule
# =============================================================================

def tips_of(project_id) -> tuple:
    """
    `(tips, elsewhere)` — the LATEST revision of every revision chain filed
    under this project, oldest schedule first; and the chains whose latest
    revision is filed under ANOTHER project.

    ⚠ **The tip, and never the revision a bill was raised on.** A revision
    exists to change what is approved, so the plan reads the schedule as it
    stands now (`ra.latest_revision()`, the helper the over-claim guard uses).
    A bill raised under an earlier revision keeps its own figures and the panel
    says so — it is not reconciled here.

    ⚠ `elsewhere` should be empty: attach and detach move a whole chain and a
    revision inherits its ancestor's project. A chain split across two projects
    (a hand-edited record) is reported, not planned, so one schedule is never
    planned on two projects.
    """
    boqs = STORE.get("boqs") or {}
    pid = str(project_id or "").strip()
    attached = sorted((b for b in boqs.values() if pid and _pid(b) == pid),
                      key=lambda b: (str(b.get("date") or ""),
                                     str(b.get("ref") or ""), str(b.get("id"))))
    tips, elsewhere, seen = [], [], set()
    for b in attached:
        tip_id = RA.latest_revision(str(b.get("id") or ""))
        if not tip_id or tip_id in seen:
            continue
        seen.add(tip_id)
        tip = boqs.get(tip_id) or {}
        (tips if _pid(tip) == pid else elsewhere).append(tip)
    return tips, elsewhere


def plan_of(boq: dict) -> dict:
    """
    One schedule's planned figures — tax-exclusive, at the NET rate and the
    BASE rate, quantity × rate per track, supply and installation.

    Per non-header line, per track:

    | the track's net rate | the quantity | revenue      | cost                           |
    |---|---|---|---|
    | None (no rate)       | any          | —            | — (a base here is COUNTED)     |
    | a number (0 too)     | None (blank) | —            | — (the line is COUNTED)        |
    | a number             | a number     | qty × net    | qty × base, if a base is there |

    ⚠ **A rate of 0 is a rate** (CLIENT_CHANGES.md §0 forty-fifth block, A1):
    a nil-priced track adds 0 to revenue and its base, if any, to cost. ⚠ **A
    missing base on a billed track is NOT a cost of 0** — the line is in
    `no_base` (`boq.lines_without_cost()`, the one rule for "cost not
    recorded") and its cost is simply not in the estimate.
    """
    revenue = cost = 0.0
    priced = base_on_unpriced = 0
    for li in boq.get("line_items") or []:
        if not isinstance(li, dict) or li.get("is_header"):
            continue
        nets = {t: BQ.net_rate(li, t) for t in TRACKS}
        # "Priced" is the population `lines_without_cost()` scans: a line
        # billed on at least one track. Its count is the M of "N of M".
        if any((n or 0.0) > 0 for n in nets.values()):
            priced += 1
        qty = _line_figure(li.get("total_qty"))
        if qty is None:
            continue                    # counted by boq.lines_without_qty()
        for t in TRACKS:
            base = _line_figure(li.get(f"{t}_base_rate"))
            if nets[t] is None:
                if base is not None:
                    base_on_unpriced += 1
                continue
            revenue += BQ.amount_of(qty, nets[t])
            if base is not None:
                cost += BQ.amount_of(qty, base)
    return {
        "boq_id": str(boq.get("id") or ""),
        "ref": str(boq.get("ref") or ""),
        "rev_no": int(boq.get("rev_no") or 0),
        "date": str(boq.get("date") or ""),
        "revenue": _paise(revenue),
        "cost": _paise(cost),
        "priced": priced,
        "no_base": BQ.lines_without_cost(boq),
        "no_rate": len(BQ.lines_not_priced(boq)),
        "no_qty": len(BQ.lines_without_qty(boq)),
        "base_on_unpriced": base_on_unpriced,
    }


def planned_of(project_id) -> dict:
    """The project's plan: every tip's own figures, and their sum."""
    tips, elsewhere = tips_of(project_id)
    plans = [plan_of(t) for t in tips]
    if not plans:
        return {"tips": [], "elsewhere": elsewhere, "revenue": None,
                "cost": None, "margin": None, "margin_pct": None,
                "priced": 0, "no_base": 0, "no_rate": 0, "no_qty": 0,
                "base_on_unpriced": 0}
    revenue = _paise(sum(p["revenue"] for p in plans))
    cost = _paise(sum(p["cost"] for p in plans))
    margin = _paise(revenue - cost)
    return {
        "tips": plans, "elsewhere": elsewhere,
        "revenue": revenue, "cost": cost, "margin": margin,
        # Guarded: a schedule whose every line is unpriced, or priced at nil,
        # plans no revenue, and a percentage of nothing is no figure at all.
        # Two decimals, half up — the house rule, so 26.25 is never shown as
        # Python's half-to-even 26.2.
        "margin_pct": (_paise(margin / revenue * 100.0) if revenue else None),
        **{k: sum(p[k] for p in plans)
           for k in ("priced", "no_base", "no_rate", "no_qty",
                     "base_on_unpriced")},
    }


# =============================================================================
# TO DATE — what was billed, and what was spent
# =============================================================================

def _bills_of(boq_ids: set) -> list:
    """Every RA bill raised against one of these BOQ revisions, run order."""
    rows = [(rid, b) for rid, b in (STORE.get("ra_bills") or {}).items()
            if str(b.get("boq_id") or "") in boq_ids]
    rows.sort(key=lambda kv: (int(kv[1].get("ra_no") or 0),
                              str(kv[1].get("ref") or ""), kv[0]))
    return rows


def _tax_invoices_of(project_id: str) -> list:
    """Every tax invoice that reaches this project through its proforma's
    `project_id` — the inheritance `/projects/view` already draws."""
    pid = str(project_id or "").strip()
    if not pid:
        return []
    proformas = STORE.get("proformas") or {}
    out = []
    for tid, ti in (STORE.get("invoices") or {}).items():
        pi = proformas.get(str(ti.get("proforma_id") or ""))
        if pi and _pid(pi) == pid:
            out.append((tid, ti))
    out.sort(key=lambda kv: (str(kv[1].get("date") or ""),
                             str(kv[1].get("ref") or ""), kv[0]))
    return out


def _po_taxable(po: dict):
    """
    A purchase order's taxable value, or `None`.

    `taxable_value` is A3's field (28 August 2026). An order written before it
    carries no charges and its taxable value IS its `subtotal` — ABOUT.md §3's
    stated rule — so that is read in its place. ⚠ Never `grand_total`: that
    includes the input tax, and a tax-inclusive figure in this section is gap
    31 again.
    """
    tv = _stored(po.get("taxable_value"))
    if tv is None and not PU.charges_of(po):
        tv = _stored(po.get("subtotal"))
    return tv


def project_pnl(project_id, include_labour: bool = True) -> dict:
    """
    Everything the Profit & Loss panel shows for one project, in three sections
    that never mix — see the module docstring for every rule.

    `include_labour` is the caller's answer to *"may this reader see wages?"*
    (`attendance.view`, CC-2 B4). False leaves site labour out of the
    arithmetic entirely and says so in `labour["withheld"]`; the totals then
    exclude it, and the panel labels them as excluding it.
    """
    pid = str(project_id or "").strip()
    boqs = STORE.get("boqs") or {}
    boq_ids = _project_boq_ids(pid)
    planned = planned_of(pid)

    # ── Billed — RA bills ───────────────────────────────────────────────────
    ra_amount, ra_count, ra_no_figure = 0.0, 0, 0
    ra_draft = ra_cancelled = 0
    issued = []
    for rid, b in _bills_of(boq_ids):
        status = RA.status_of(b)
        if status == "draft":
            ra_draft += 1
            continue
        if status == "cancelled":
            ra_cancelled += 1
            continue
        issued.append((rid, b))
        taxable = _stored(b.get("claim_subtotal"))
        if taxable is None:
            ra_no_figure += 1
            continue
        ra_amount += taxable
        ra_count += 1

    # ⚠ A bill raised under an EARLIER revision than its chain's tip. Its own
    #   figures stand — they are what was billed — and the plan reads the tip;
    #   the two may legitimately disagree, and the panel says so rather than
    #   reconciling them (`ra.party_drift()`'s shape).
    earlier = []
    for rid, b in issued:
        on = str(b.get("boq_id") or "")
        tip_id = RA.latest_revision(on)
        if tip_id and tip_id != on:
            tip = boqs.get(tip_id) or {}
            earlier.append({
                "ref": str(b.get("ref") or ""),
                "boq_ref": str(b.get("boq_ref") or (boqs.get(on) or {}).get("ref") or ""),
                "rev_no": int(b.get("boq_rev_no") if b.get("boq_rev_no") is not None
                              else (boqs.get(on) or {}).get("rev_no") or 0),
                "tip_ref": str(tip.get("ref") or ""),
                "tip_rev_no": int(tip.get("rev_no") or 0),
                "tip_date": str(tip.get("date") or ""),
            })

    # ⚠ The merged RA: a NOTE and never money. Its legs are counted above,
    #   once each; its own totals are their sum (CC-2 C3), so adding it would
    #   count both bills twice.
    merged, seen_merged = [], set()
    for rid, _b in issued:
        m = MRA.live_merge_of(rid)
        if m and m.get("id") not in seen_merged:
            seen_merged.add(m.get("id"))
            merged.append({"ref": str(m.get("tax_invoice_ref") or ""),
                           "legs": [str(m.get("supply_ref") or ""),
                                    str(m.get("installation_ref") or "")],
                           "grand_total": _stored(m.get("grand_total"))})

    # ── Billed — tax invoices through a proforma ────────────────────────────
    ra_serials = {}
    for _rid, b in issued:
        k = _serial(b.get("tax_invoice_ref"))
        if k:
            ra_serials.setdefault(k, b)
    ti_amount, ti_grand, ti_count, ti_no_figure, ti_cancelled = 0.0, 0.0, 0, 0, 0
    ti_no_grand = 0
    same_number = []
    for _tid, ti in _tax_invoices_of(pid):
        if str(ti.get("status") or "") == "cancelled":
            ti_cancelled += 1
            continue
        twin = ra_serials.get(_serial(ti.get("ref")))
        if twin is not None:
            same_number.append({"ti_ref": str(ti.get("ref") or ""),
                                "ra_ref": str(twin.get("ref") or ""),
                                "taxable": _stored(ti.get("subtotal"))})
            continue
        taxable = _stored(ti.get("subtotal"))
        if taxable is None:
            ti_no_figure += 1
            continue
        ti_amount += taxable
        ti_count += 1
        grand = _stored(ti.get("grand_total"))
        if grand is None:
            ti_no_grand += 1
        else:
            ti_grand += grand

    # ── Actual cost — purchase orders ───────────────────────────────────────
    po_amount, po_exempt, po_count, po_exempt_count, po_no_figure = 0.0, 0.0, 0, 0, 0
    po_draft_status = po_cancelled = po_unknown = 0
    for po in (STORE.get("purchases") or {}).values():
        if not pid or _pid(po) != pid:
            continue
        # `purchase.py`'s own reading: a missing status is its default, Draft.
        status = str(po.get("status") or "") or PU.DEFAULT_STATUS
        if status not in COMMITTED_PO_STATUSES:
            if status == "Draft":
                po_draft_status += 1
            elif status == "Cancelled":
                po_cancelled += 1
            else:
                po_unknown += 1
            continue
        taxable = _po_taxable(po)
        if taxable is None:
            po_no_figure += 1
        else:
            po_amount += taxable
            po_count += 1
        exempt = PU.charge_totals(PU.charges_of(po))[1]
        if exempt:
            po_exempt += exempt
            po_exempt_count += 1

    # A draft purchase order sent out for pricing (`po_draft.py`) is an INTENT:
    # it carries no rate and is never a cost. Counted so the panel can say it
    # was left out on purpose, never priced.
    po_drafts = sum(1 for d in (STORE.get("purchase_orders") or {}).values()
                    if str(d.get("boq_id") or "") in boq_ids)

    # ── Actual cost — work orders, its OWN row (ABOUT.md §7 gap 55) ─────────
    wo_amount, wo_count, wo_draft, wo_cancelled = 0.0, 0, 0, 0
    for wo in (STORE.get("work_orders") or {}).values():
        if not pid or _pid(wo) != pid:
            continue
        status = WO.status_of(wo)
        if status == "issued":
            wo_amount += WO.totals_of(wo)["grand"]
            wo_count += 1
        elif status == "draft":
            wo_draft += 1
        else:
            wo_cancelled += 1

    # ── Actual cost — charges ───────────────────────────────────────────────
    ch_amount, ch_count, ch_no_figure = 0.0, 0, 0
    for c in (STORE.get("charges") or {}).values():
        if not pid or _pid(c) != pid:
            continue
        taxable = _stored(c.get("taxable_amount"))
        if taxable is None:
            ch_no_figure += 1
            continue
        ch_amount += taxable
        ch_count += 1

    # ── Actual cost — site labour, priced by attendance.py itself ───────────
    if include_labour:
        labour = dict(AT.labour_cost_of(AT.markings_for_project(pid)),
                      withheld=False)
    else:
        labour = {"total": None, "markings": 0, "costed": 0, "refused": 0,
                  "withheld": True}

    billed = _paise(ra_amount + ti_amount)
    actual = _paise(po_amount + po_exempt + wo_amount + ch_amount
                    + (labour["total"] or 0.0))

    # ── Cash — GST-INCLUSIVE, and the RA bills only ─────────────────────────
    # Receipts are recorded against RA bills and nothing else in this app, so
    # a tax invoice's payment is not on record anywhere; its GST-inclusive
    # value is reported beside the section and kept out of its outstanding.
    cash_billed = cash_received = cash_written_off = cash_outstanding = 0.0
    cash_count = cash_no_figure = 0
    for rid, b in issued:
        if _stored(b.get("grand_total")) is None:
            cash_no_figure += 1
            continue
        cash_count += 1
        cash_billed += _stored(b.get("grand_total"))
        cash_received += RA.received_against(rid)
        cash_written_off += RA.written_off_against(rid)
        cash_outstanding += RA.outstanding_of(b)

    return {
        "project_id": pid,
        "planned": planned,
        "to_date": {
            "ra": {"amount": _paise(ra_amount), "count": ra_count,
                   "no_figure": ra_no_figure},
            "ti": {"amount": _paise(ti_amount), "count": ti_count,
                   "no_figure": ti_no_figure},
            "billed": billed,
            "po": {"amount": _paise(po_amount), "count": po_count,
                   "no_figure": po_no_figure},
            "po_exempt": {"amount": _paise(po_exempt), "count": po_exempt_count},
            "wo": {"amount": _paise(wo_amount), "count": wo_count},
            "charges": {"amount": _paise(ch_amount), "count": ch_count,
                        "no_figure": ch_no_figure},
            "labour": labour,
            "actual": actual,
            "margin": _paise(billed - actual),
            # Estimate less actual: what the estimate has not yet been spent
            # on — negative once actual cost has passed it. A DIFFERENCE,
            # labelled as one; the two figures are never blended.
            "variance": (_paise(planned["cost"] - actual)
                         if planned["cost"] is not None else None),
        },
        "excluded": {
            "ra_draft": ra_draft, "ra_cancelled": ra_cancelled,
            "ti_cancelled": ti_cancelled,
            "po_draft_status": po_draft_status, "po_cancelled": po_cancelled,
            "po_unknown": po_unknown, "po_drafts": po_drafts,
            "wo_draft": wo_draft, "wo_cancelled": wo_cancelled,
        },
        "same_number": same_number,
        "earlier_revision": earlier,
        "merged": merged,
        "cash": {
            "billed": _paise(cash_billed), "received": _paise(cash_received),
            "written_off": _paise(cash_written_off),
            "outstanding": _paise(cash_outstanding),
            "count": cash_count, "no_figure": cash_no_figure,
            "ti_billed": _paise(ti_grand), "ti_count": ti_count,
            "ti_no_figure": ti_no_grand,
        },
    }


# =============================================================================
# COST TAGGED TO NO PROJECT — the line under the `/projects` register
# =============================================================================

def untagged_cost(include_labour: bool = True) -> dict:
    """
    Every cost tagged to NO LIVE project — the same four sources and the same
    statuses as a project's actual cost, tax-exclusive.

    ⚠ **The 16 August 2026 ruling, and ABOUT.md §7 gap B5: untagged cost must
    not vanish.** A per-project cost is understated by every order somebody
    forgot to tag, so the untagged total is shown on its own line — never
    filtered out, never spread across the projects that were tagged. A
    `project_id` naming a project that no longer exists is on no project's page
    either, so it is counted here too, and `dangling` says how many.
    """
    live = set((STORE.get("projects") or {}).keys())

    def _untagged(rec) -> bool:
        return _pid(rec) not in live

    def _dangling(rec) -> bool:
        return bool(_pid(rec)) and _pid(rec) not in live

    po_amount, po_count, dangling, no_figure = 0.0, 0, 0, 0
    for po in (STORE.get("purchases") or {}).values():
        status = str(po.get("status") or "") or PU.DEFAULT_STATUS
        if status not in COMMITTED_PO_STATUSES or not _untagged(po):
            continue
        dangling += _dangling(po)
        taxable = _po_taxable(po)
        if taxable is None:
            no_figure += 1
            continue
        po_amount += taxable + PU.charge_totals(PU.charges_of(po))[1]
        po_count += 1

    wo_amount, wo_count = 0.0, 0
    for wo in (STORE.get("work_orders") or {}).values():
        if WO.status_of(wo) != "issued" or not _untagged(wo):
            continue
        wo_amount += WO.totals_of(wo)["grand"]
        wo_count += 1
        dangling += _dangling(wo)

    ch_amount, ch_count = 0.0, 0
    for c in (STORE.get("charges") or {}).values():
        if not _untagged(c):
            continue
        dangling += _dangling(c)
        taxable = _stored(c.get("taxable_amount"))
        if taxable is None:
            no_figure += 1
            continue
        ch_amount += taxable
        ch_count += 1

    if include_labour:
        rows = AT.markings_on_no_project()
        labour = dict(AT.labour_cost_of(rows), withheld=False)
        dangling += sum(1 for r in rows if _dangling(r))
    else:
        labour = {"total": None, "markings": 0, "costed": 0, "refused": 0,
                  "withheld": True}

    return {
        "po": {"amount": _paise(po_amount), "count": po_count},
        "wo": {"amount": _paise(wo_amount), "count": wo_count},
        "charges": {"amount": _paise(ch_amount), "count": ch_count},
        "labour": labour,
        "total": _paise(po_amount + wo_amount + ch_amount
                        + (labour["total"] or 0.0)),
        "dangling": dangling,
        "no_figure": no_figure,
    }


def register_line_html(u: dict) -> str:
    """
    The one sentence under the `/projects` register. ⚠ No user text reaches
    it — figures and counts only — so nothing here needs escaping; a money
    format is never escaped (ABOUT.md §9).

    Starts with a newline and carries its own inline style, so the register's
    `<style>` block is untouched and the caller can splice it in where an
    empty string leaves the page byte-for-byte as it was.
    """
    def _r(v) -> str:
        return f"&#8377;&nbsp;{_inr(v)}"

    parts = [f"committed purchase orders {_r(u['po']['amount'])}",
             f"issued work orders {_r(u['wo']['amount'])}",
             f"charges {_r(u['charges']['amount'])}"]
    if u["labour"]["withheld"]:
        parts.append("site labour not shown &mdash; it needs the <b>View "
                     "attendance</b> permission")
    else:
        parts.append(f"site labour {_r(u['labour']['total'])}")
    refused = u["labour"].get("refused") or 0
    short = (f' {refused} marking{"" if refused == 1 else "s"} predate'
             f'{"s" if refused == 1 else ""} the day-rate correction and '
             f'{"is" if refused == 1 else "are"} not costed.' if refused else "")
    dangling = u.get("dangling") or 0
    gone = (f' {dangling} of these records name{"s" if dangling == 1 else ""} '
            f'a project that no longer exists.' if dangling else "")
    blank = u.get("no_figure") or 0
    unfigured = (f' {blank} record{"" if blank == 1 else "s"} '
                 f'carr{"ies" if blank == 1 else "y"} no stored figure and '
                 f'{"is" if blank == 1 else "are"} not in the total.'
                 if blank else "")
    return (
        f'\n        <p class="proj-untagged" style="margin:1rem 0 0;'
        f'font-size:.86rem;line-height:1.6;color:#555;">'
        f'<b style="color:var(--navy);">Cost not tagged to any project: '
        f'{_r(u["total"])}</b> &mdash; tax-exclusive: {", ".join(parts)}.'
        f'{short}{gone}{unfigured} It is on no project&rsquo;s profit and '
        f'loss; tag each record to its project to put it there.</p>')
