"""
projtag.py — filing a LOOSE document under a project, by hand
=============================================================
No routes and no blueprint. `projectview.py` owns the *Attach document*
control; this module owns **which documents may be attached, what the write
is, and what the refusal says**.

CLIENT_CHANGES.md §0's **fifty-eighth** block, item 3. The client's ask from
the 28 October 2026 Yogesh meeting: a purchase order, proforma, work order or
charge that was **never raised from a BOQ** should be filable under a project
from the project's own page. Before this there was no way at all — those four
forms carry a project picker at **create** and nothing afterwards, and three of
the four modules have no edit screen that offers it.

Why it is its own module, and not four edits
--------------------------------------------
⚠ **`purchase.py` and `proforma.py` are being edited on an unpushed office-PC
line** and this pass is under instruction to leave them alone. Writing a
`project_id` onto an existing record **from here** is preferred to editing
four page modules, and it has an independent merit: the trail entry, the
refusal and the candidate rule are then **one definition** instead of four
that can drift. `workorder.py` and `charge.py` are untouched for the same
reason, not because they are protected.

`pnl.project_of()` IS the answer, and this asks it
--------------------------------------------------
⚠ **There is exactly one answer to "which project is this document on", and it
is not here.** `pnl.project_of()` (28 October 2026, `a6ab6c4`) derives it: a
document whose `boq_id` resolves to a live schedule belongs to **that BOQ's
project as it stands now**, a tax invoice otherwise follows its proforma, and
anything else keeps the `project_id` a person chose. This module **reads** that
function and adds no second rule — so the attach list, the project page's
panels, the P&L and the untagged-cost line cannot disagree.

⚠ **A DOCUMENT THAT DERIVES ITS PROJECT FROM A BOQ IS REFUSED, and the refusal
says why.** It follows its schedule, and a hand tag that disagreed with its BOQ
would be a second answer to a question that has one — `project_of()` would go
on reporting the BOQ's project while the record carried something else, and the
two pages that read it would print different truths. Attach or detach the
**BOQ** instead, on the same page, which moves everything raised from it.

⚠ **A TAX INVOICE IS NOT IN THE LIST.** It inherits through its proforma **at
read time** and nothing is written on it (`project_of(ti, "invoice")`). Tagging
one by hand would be the same second answer one document further along; moving
its proforma moves it.

The trail
---------
⚠ **ONE field, `project_trail`, written from one place.** Who, when, from which
project, to which — appended, never edited, never deleted, the shape
`purchase.py`'s `status_history` and `auth.py`'s `access_history` already use.
It is deliberately **not** each module's own trail field: `purchase.py` has
`status_history`, the other three have nothing at all, and writing four
different shapes from here is how the record of who moved what stops being
readable. A record with no key has never been moved by hand, and nothing is
backfilled.

Import direction — a LEAF above `pnl.py`
----------------------------------------
    projtag.py ──► pnl.py       project_of(), the one reader
    projtag.py ──► pipeline.py  esc
    projtag.py ──► store        the shared STORE dict

`projectview.py` imports this; nothing else does, and this imports no page
module — not `purchase.py`, not `proforma.py`, not `workorder.py`, not
`charge.py`. Their records arrive as the dicts they are, which is
`lineimage.py`'s arrangement one register along: the leaf is handed a record
and knows nothing about the document it belongs to.
"""

from datetime import datetime

import pipeline as P
import pnl as PNL
from store import STORE

# ⚠ The trail field. One name, read and written here and nowhere else.
TRAIL_FIELD = "project_trail"

ATTACH = "attach"
DETACH = "detach"


class Kind:
    """One attachable document type: where it lives and how it reads."""

    __slots__ = ("key", "collection", "label", "plural", "ref_key",
                 "name_key", "of_kind")

    def __init__(self, key, collection, label, plural, ref_key,
                 name_key="project_name", of_kind=""):
        self.key = key
        self.collection = collection
        self.label = label
        self.plural = plural
        self.ref_key = ref_key
        # ⚠ All four snapshot the project's NAME beside its id — `charge.py`'s
        #   pattern, which `purchase.py` and `workorder.py` follow. It is kept
        #   in step here so a row that was attached by hand reads the same as
        #   one tagged at create.
        self.name_key = name_key
        # What `pnl.project_of()` is told this record is. Only the tax invoice
        # has a kind, and the tax invoice is deliberately not attachable.
        self.of_kind = of_kind


KINDS = {
    k.key: k for k in (
        Kind("purchase", "purchases", "Purchase order", "purchase orders", "ref"),
        Kind("proforma", "proformas", "Proforma invoice", "proforma invoices", "ref"),
        Kind("workorder", "work_orders", "Work order", "work orders", "ref"),
        # ⚠ A charge has no document number. `person` is what the project
        #   page's own Expenses panel links on, so it is what names a row here.
        Kind("charge", "charges", "Charge", "charges", "person"),
    )
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _records(kind: str) -> dict:
    k = KINDS.get(kind)
    return (STORE.get(k.collection) or {}) if k else {}


def get(kind: str, doc_id: str) -> dict:
    return _records(kind).get(str(doc_id or "")) or {}


def project_of(kind: str, rec: dict) -> str:
    """Which project this document is on — `pnl.project_of()`, and nothing
    else. See the module docstring."""
    k = KINDS.get(kind)
    return PNL.project_of(rec, k.of_kind if k else "")


def derives_from_boq(rec: dict) -> str:
    """
    The **ref of the schedule this document follows**, or `""` when it follows
    none — which is the whole of the attach refusal.

    ⚠ **It asks whether `boq_id` RESOLVES, which is `project_of()`'s own
      test**, not merely whether the field is set. A `boq_id` naming a schedule
      that was deleted falls through to the stored tag there, so such a record
      **is** hand-taggable here; the two must agree or a document could be
      refused by this function and still be reported untagged by that one.
    """
    boq = (STORE.get("boqs") or {}).get(str((rec or {}).get("boq_id") or ""))
    if boq is None:
        return ""
    # A schedule with no ref of its own still follows a BOQ; the caller needs a
    # non-empty answer, so fall back to the id.
    return str(boq.get("ref") or "").strip() or str(boq.get("id") or "") or "?"


def label_of(kind: str, rec: dict) -> str:
    k = KINDS.get(kind)
    if not k:
        return ""
    return str((rec or {}).get(k.ref_key) or "").strip()


def candidates() -> dict:
    """
    `{kind: [(doc_id, rec), …]}` — every document that may be attached: one
    that follows **no** BOQ and is on **no live project**.

    ⚠ **"No live project" and not "a blank tag".** A `project_id` naming a
      project that no longer exists is on no project's page and is in the
      untagged total, so it is offered — `projectview.py`'s own eligible-BOQ
      rule of 9 September 2026, which exists because deleting a project leaves
      every record filed under it pointing at nothing and otherwise
      unreachable from any screen.

    Date order where the record has a date, then by label, so the picker reads
    the way the panels above it do.
    """
    live = STORE.get("projects") or {}
    out = {}
    for key, k in KINDS.items():
        rows = []
        for did, rec in _records(key).items():
            if derives_from_boq(rec):
                continue
            if str(rec.get("project_id") or "").strip() in live and \
                    str(rec.get("project_id") or "").strip():
                continue
            rows.append((did, rec))
        rows.sort(key=lambda kv: (str(kv[1].get("date")
                                      or kv[1].get("created_at") or ""),
                                  label_of(key, kv[1]).lower()), reverse=True)
        out[key] = rows
    return out


def attached(project_id: str) -> dict:
    """
    `{kind: [(doc_id, rec), …]}` — what is on this project **by a hand tag**,
    so it can be detached again.

    ⚠ **A document following a BOQ is NOT listed**, even though it is on this
      project: detaching it is meaningless because `project_of()` would put it
      straight back. The BOQ panel's own Detach is how those move, and it moves
      the whole chain.
    """
    pid = str(project_id or "").strip()
    out = {k: [] for k in KINDS}
    if not pid:
        return out
    for key in KINDS:
        rows = [(did, rec) for did, rec in _records(key).items()
                if not derives_from_boq(rec)
                and str(rec.get("project_id") or "").strip() == pid]
        rows.sort(key=lambda kv: (str(kv[1].get("date")
                                      or kv[1].get("created_at") or ""),
                                  label_of(key, kv[1]).lower()), reverse=True)
        out[key] = rows
    return out


def _log(rec: dict, action: str, frm: str, to: str, who: str) -> dict:
    """
    Append one entry to this record's project trail — who, when, from, to.

    ⚠ **Appended and never edited.** The project NAMES are snapshotted beside
      the ids for the reason every snapshot in this app exists: the trail has
      to still read correctly when a project is renamed or deleted, and an id
      alone would then say nothing.
    """
    projects = STORE.get("projects") or {}
    entry = {
        "at": _now(),
        "by": str(who or "").strip() or "unknown",
        "action": action,
        "from": frm,
        "from_name": str((projects.get(frm) or {}).get("name") or ""),
        "to": to,
        "to_name": str((projects.get(to) or {}).get("name") or ""),
    }
    rec.setdefault(TRAIL_FIELD, []).append(entry)
    return entry


def trail_of(rec: dict) -> list:
    """This record's project trail, newest first. `[]` on a record never moved
    by hand — absent means exactly that and nothing is backfilled."""
    return list(reversed((rec or {}).get(TRAIL_FIELD) or []))


def attach(kind: str, doc_id: str, project_id: str, who: str = "") -> tuple:
    """
    `(message, error)` — file this document under this project.

    Every refusal names what is wrong with **this document** rather than
    returning a generic no, `merged_ra.can_merge()`'s rule: the operator is
    choosing off a picker and needs to know which half to change.
    """
    k = KINDS.get(kind)
    if not k:
        return "", "That is not a kind of document that can be attached."
    rec = get(kind, doc_id)
    if not rec:
        return "", f"That {k.label.lower()} no longer exists."
    proj = (STORE.get("projects") or {}).get(str(project_id or "").strip())
    if not proj:
        return "", "That project no longer exists."

    # ⚠ THE REFUSAL, and it says why rather than just refusing.
    boq_ref = derives_from_boq(rec)
    if boq_ref:
        return "", (
            f"{k.label} {label_of(kind, rec) or '(no ref)'} was raised from "
            f"schedule {boq_ref}, so it follows that schedule's project and "
            f"cannot be filed by hand — a hand tag that disagreed with its BOQ "
            f"would be a second answer to a question that has one. Attach or "
            f"detach the BOQ instead, on this page: that moves everything "
            f"raised from it.")

    frm = str(rec.get("project_id") or "").strip()
    if frm == proj["id"]:
        return "", (f"{k.label} {label_of(kind, rec) or '(no ref)'} is already "
                    f"filed under this project.")

    rec["project_id"] = proj["id"]
    if k.name_key:
        rec[k.name_key] = str(proj.get("name") or "")
    _log(rec, ATTACH, frm, proj["id"], who)
    return (f"{k.label} {label_of(kind, rec) or '(no ref)'} filed under "
            f"{proj.get('name')}."), ""


def detach(kind: str, doc_id: str, project_id: str, who: str = "") -> tuple:
    """
    `(message, error)` — put this document back in the untagged pool.

    ⚠ **Only a document currently on THIS project is cleared.** One filed
      elsewhere is left alone rather than silently detached from a project this
      page is not looking at — DOMAIN.md §6's rule, and exactly what
      `projectview.py`'s BOQ detach branch already does.
    """
    k = KINDS.get(kind)
    if not k:
        return "", "That is not a kind of document that can be detached."
    rec = get(kind, doc_id)
    if not rec:
        return "", f"That {k.label.lower()} no longer exists."
    pid = str(project_id or "").strip()

    boq_ref = derives_from_boq(rec)
    if boq_ref:
        return "", (
            f"{k.label} {label_of(kind, rec) or '(no ref)'} follows schedule "
            f"{boq_ref} and is not filed by hand, so there is no hand tag to "
            f"remove. Detach the BOQ on this page instead, which moves "
            f"everything raised from it.")

    if str(rec.get("project_id") or "").strip() != pid or not pid:
        return "", (f"{k.label} {label_of(kind, rec) or '(no ref)'} is not "
                    f"filed under this project.")

    rec["project_id"] = ""
    if k.name_key:
        rec[k.name_key] = ""
    _log(rec, DETACH, pid, "", who)
    return (f"{k.label} {label_of(kind, rec) or '(no ref)'} detached from this "
            f"project. It can now be filed under another."), ""


# =============================================================================
# THE CONTROL — rendered here so the four kinds cannot drift into four designs
# =============================================================================

def _options(rows, kind: str) -> str:
    """One `<option>` per row, value `kind:id`. No placeholder — the caller
    writes that once, outside the groups."""
    out = ""
    for did, rec in rows:
        when = str(rec.get("date") or rec.get("created_at") or "")[:10]
        out += (f'<option value="{kind}:{P.esc(did)}">'
                f'{P.esc(label_of(kind, rec)) or "(no ref)"}'
                f'{" &middot; " + P.esc(when) if when else ""}</option>')
    return out


def picker_html(project_id: str, form_action: str) -> str:
    """
    The *Attach document* / *Detach* block for `/projects/view/<id>`.

    ⚠ **One `<optgroup>` per kind inside ONE select**, so the value carries
      `kind:id` and the POST cannot be handed an id without the collection it
      came from. Four selects would be four chances to post a work order id
      against the purchases collection.
    """
    cand = candidates()
    held = attached(project_id)

    def _groups(bundle) -> str:
        out = ""
        for key, k in KINDS.items():
            rows = bundle.get(key) or []
            if not rows:
                continue
            out += (f'<optgroup label="{P.esc(k.plural.title())}">'
                    f'{_options(rows, key)}</optgroup>')
        return out

    a_groups = _groups(cand)
    d_groups = _groups(held)

    # ⚠ **`min-width` on the select is what put this panel into a horizontal
    #   scrollbar at 390 px.** Measured in headless Chromium: the select at
    #   260 px plus the button plus the panel's padding ran ~56 px past a
    #   390 px viewport. `flex-wrap` plus `max-width` and `min-width:0` lets
    #   the row break and the select shrink instead; at 1280 px it is
    #   unchanged. (The `table.data` panels above it overflow at 390 px too
    #   and that is NOT this pass's — ABOUT.md §7, recorded separately.)
    _sel = ("flex:1 1 200px;min-width:0;max-width:260px;")
    _row = "display:flex;gap:.5rem;flex-wrap:wrap;max-width:100%;"
    attach_ctl = (
        f'<form method="POST" action="{form_action}" style="{_row}">'
        f'<input type="hidden" name="action" value="attach_doc">'
        f'<select name="doc" class="form-control" style="{_sel}" required>'
        f'<option value="">-- Select an untagged document --</option>'
        f'{a_groups}</select>'
        f'<button type="submit" class="btn btn-ghost">Attach</button></form>'
        if a_groups else
        '<p style="margin:0;font-size:.82rem;color:var(--muted);">Every purchase '
        'order, proforma, work order and charge is already filed under a project '
        'or follows a schedule. Nothing is waiting to be attached.</p>')

    detach_ctl = (
        f'<form method="POST" action="{form_action}" style="{_row}">'
        f'<input type="hidden" name="action" value="detach_doc">'
        f'<select name="doc" class="form-control" style="{_sel}" required>'
        f'<option value="">-- Select a document filed by hand --</option>'
        f'{d_groups}</select>'
        f'<button type="submit" class="btn btn-ghost">Detach</button></form>'
        if d_groups else
        '<p style="margin:0;font-size:.82rem;color:var(--muted);">Nothing on this '
        'project was filed by hand. A document raised from one of its schedules '
        'follows that schedule and is detached with the BOQ.</p>')

    return f"""
    <div class="panel">
      <div class="panel-head">
        <h2>Attach document</h2>
        <span style="font-size:0.8rem;color:var(--muted);">A purchase order, proforma, work order or charge raised on its own &mdash; not from a schedule</span>
      </div>
      <p style="margin:0 0 1rem;font-size:.83rem;color:var(--muted);line-height:1.6;">
        A document <b>raised from a BOQ follows that schedule&rsquo;s project</b>
        and is not offered here &mdash; attach or detach the BOQ above instead,
        which moves everything raised from it. A <b>tax invoice</b> inherits
        through its proforma when the page is read and carries no tag of its own.
        Every attach and detach is written on the document&rsquo;s own trail.
      </p>
      <div style="background:var(--surface); padding:1rem; border-radius:6px; display:flex; flex-wrap:wrap; gap:1.5rem; align-items:flex-end;">
        <div style="flex:1 1 260px; min-width:0;">
          <p style="margin:0 0 0.5rem 0; font-weight:600; font-size:0.9rem;">File under this project</p>
          {attach_ctl}
        </div>
        <div style="flex:1 1 260px; min-width:0; border-left:1px solid var(--border); padding-left:1.5rem;">
          <p style="margin:0 0 0.5rem 0; font-weight:600; font-size:0.9rem;">Remove a hand-filed document</p>
          {detach_ctl}
        </div>
      </div>
    </div>"""
