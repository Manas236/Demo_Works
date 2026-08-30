"""
projectview.py — Project Detail Page
====================================
Blueprint  : projectview_bp
Mounted at : /projects (registered in app.py)

This module replaces the dummy view in project.py.
It displays project metadata and gathers documents attached to the project.

Each panel shows the documents' OWN values and adds that one column up. What
this page must never show is a figure that only exists by combining two panels
— no revenue total, no cost total, no margin, no profit, no net, no balance.
The page reads what the sell side billed and what the buy side committed side
by side; it does not do the subtraction, because the moment it does, the
project page becomes a P&L that nobody signed off on.
"""

from flask import Blueprint, redirect, request, url_for
import auth
import branding as B
import pipeline as P
import project as PJ
from store import STORE
from dashboard import BASE_STYLES, _nav
from quotation import QUOTATION_STYLES, _inr
from ra import revision_chain

projectview_bp = Blueprint("projectview", __name__, url_prefix="/projects")

def _page(html: str) -> str:
    return html


def _total_of(doc: dict, key: str):
    """
    A document's OWN stored total, as a float, or `None` when the record does
    not carry one.

    Nothing here recomputes a figure from line items. Every document that
    reaches this page froze its own total when it was written — a proforma, a
    tax invoice and a purchase order each store `grand_total`, a BOQ stores
    `subtotal` — and a second arithmetic path is exactly how two copies of one
    number start to disagree. `None` is not `0.0`: a record with no total has
    nothing to say, and saying "0.00" for it would invent a fact.
    """
    raw = doc.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _amt(v) -> str:
    """One stored total in Indian digit grouping, no symbol (§9). Absent stays
    the em-dash this page already uses for an empty cell."""
    return _inr(v) if v is not None else "—"


def _sum_cell(vals: list) -> str:
    """
    One panel's own column added up.

    A sum down a single panel, never across two. The records that carry no
    total sit the sum out rather than counting as zero, and a panel where
    nothing carries a total totals to an em-dash.
    """
    present = [v for v in vals if v is not None]
    return _inr(sum(present)) if present else "—"


def _total_row(span: int, cell: str) -> str:
    """The `Total` line under one panel's table. `span` is the label's width."""
    return (f'<tr class="total-row"><td colspan="{span}">Total</td>'
            f'<td style="text-align:right;">{cell}</td></tr>')

def _alert(msg: str, kind: str = "error") -> str:
    if not msg:
        return ""
    icon = "&#10003;" if kind == "success" else "&#10007;"
    return f'<div class="alert alert-{P.esc(kind)}">{icon} {P.esc(msg)}</div>'

@projectview_bp.route("/view/<id>", methods=["GET", "POST"])
def view_project(id: str):
    proj = STORE.get("projects", {}).get(id)
    if not proj:
        return redirect(url_for("project.list_projects",
                                msg="Project not found.", type="error"))

    if request.method == "POST":
        # ⚠ **This branch WRITES, and the route is classified `project.view`.**
        #
        # `auth.ROUTE_PERMISSIONS` maps an *endpoint* to a permission, and this
        # rule answers GET and POST on one endpoint — so without this guard the
        # read permission authorises the write below, which reassigns
        # `project_id` on every BOQ in a revision chain. Sales Manager,
        # Purchase Manager and Accountant all hold `project.view` and none
        # holds `project.edit`: all three are refused `/projects/edit/<id>`
        # and could re-attach any schedule to any project through this page.
        #
        # The registry cannot express "this permission for GET, that one for
        # POST", so this is a per-view guard — the same shape ABOUT.md §7 gap
        # 24 prescribes for the object-level checks B6 will need. The endpoint
        # stays on `project.view` because reading the page is genuinely a read;
        # only the POST is raised to `project.edit`.
        #
        # `tests/test_access_control_adversarial.py` holds both halves: the
        # refusal, and the control that a `project.edit` holder still attaches.
        if not auth.has_perm("project.edit"):
            auth._log_refusal(auth.current_user(), request.endpoint,
                              "project.edit", "write on a read-gated route")
            return auth._refusal_page(
                "You do not have access to change this project",
                "Attaching a schedule to a project is a change rather than a "
                "reading of one, so it needs the <b>Edit a project</b> "
                "permission (<code>project.edit</code>) &mdash; viewing this "
                "page only needs <code>project.view</code>. Ask an "
                "administrator to add it to one of your roles."), 403

        action = request.form.get("action")
        if action == "attach_boq":
            boq_id = request.form.get("boq_id")
            if boq_id:
                # Attach entire revision chain
                chain = revision_chain(boq_id)
                for c_id in chain:
                    b = STORE["boqs"].get(c_id)
                    if b:
                        b["project_id"] = id
                return redirect(url_for("projectview.view_project", id=id,
                                        msg="BOQ chain attached to project.", type="success"))
            else:
                return redirect(url_for("projectview.view_project", id=id,
                                        msg="No BOQ selected.", type="error"))

    msg = request.args.get("msg")
    msg_type = request.args.get("type", "success")
    
    # ── Gather Attached Documents ─────────────────────────────────────────────
    # BOQs
    attached_boqs = [b for b in STORE.get("boqs", {}).values() if b.get("project_id") == id]
    attached_boqs.sort(key=lambda b: (str(b.get("date") or ""), str(b.get("ref") or "")), reverse=True)
    
    boq_html = ""
    boq_vals = []
    for boq in attached_boqs:
        # A BOQ stores its trio at §4.3; `subtotal` is the one the sheet prints.
        val = _total_of(boq, "subtotal")
        boq_vals.append(val)
        boq_html += f"""
        <tr>
          <td><a href="{url_for('boq.view_boq', id=boq.get('id'))}"><b>{P.esc(boq.get('ref'))}</b></a></td>
          <td>{P.esc(boq.get('date'))}</td>
          <td>Rev {int(boq.get('rev_no') or 0)}</td>
          <td>{P.esc(boq.get('account_name') or '—')}</td>
          <td style="text-align:right;">{_amt(val)}</td>
        </tr>
        """
    if attached_boqs:
        boq_html += _total_row(4, _sum_cell(boq_vals))
    else:
        boq_html = '<tr><td colspan="5" style="color:var(--muted);">No schedules attached.</td></tr>'

    # Proformas
    attached_pis = [pi for pi in STORE.get("proformas", {}).values() if pi.get("project_id") == id]
    attached_pis.sort(key=lambda p: (str(p.get("date") or ""), str(p.get("ref") or "")), reverse=True)
    pi_html = ""
    pi_vals = []
    for pi in attached_pis:
        val = _total_of(pi, "grand_total")
        pi_vals.append(val)
        pi_html += f"""
        <tr>
          <td><a href="{url_for('proforma.view_proforma', id=pi.get('id'))}"><b>{P.esc(pi.get('ref'))}</b></a></td>
          <td>{P.esc(pi.get('date'))}</td>
          <td>{P.esc(pi.get('account_name') or '—')}</td>
          <td style="text-align:right;">{_amt(val)}</td>
        </tr>
        """
    if attached_pis:
        pi_html += _total_row(3, _sum_cell(pi_vals))
    else:
        pi_html = '<tr><td colspan="4" style="color:var(--muted);">No proforma invoices attached.</td></tr>'

    # Tax Invoices (inheriting via proforma)
    attached_tis = []
    for ti in STORE.get("invoices", {}).values():
        pi_id = ti.get("proforma_id")
        if pi_id:
            pi = STORE.get("proformas", {}).get(pi_id)
            if pi and pi.get("project_id") == id:
                attached_tis.append(ti)
                
    attached_tis.sort(key=lambda t: (str(t.get("date") or ""), str(t.get("ref") or "")), reverse=True)
    ti_html = ""
    ti_vals = []
    for ti in attached_tis:
        val = _total_of(ti, "grand_total")
        ti_vals.append(val)
        ti_html += f"""
        <tr>
          <td><a href="{url_for('invoice.view_invoice', id=ti.get('id'))}"><b>{P.esc(ti.get('ref'))}</b></a></td>
          <td>{P.esc(ti.get('date'))}</td>
          <td>{P.esc(ti.get('account_name') or '—')}</td>
          <td style="text-align:right;">{_amt(val)}</td>
        </tr>
        """
    if attached_tis:
        ti_html += _total_row(3, _sum_cell(ti_vals))
    else:
        ti_html = '<tr><td colspan="4" style="color:var(--muted);">No tax invoices attached.</td></tr>'

    # Purchase Orders
    attached_pos = [po for po in STORE.get("purchases", {}).values() if po.get("project_id") == id]
    attached_pos.sort(key=lambda p: (str(p.get("date") or ""), str(p.get("ref") or "")), reverse=True)
    po_html = ""
    po_vals = []
    for po in attached_pos:
        # `purchase.py` writes `vendor_name` — the buy side buys from a vendor,
        # and nothing in the app has ever written `supplier_name`. The old key
        # is kept as a fallback so a hand-edited record still shows a name
        # rather than silently going blank the way this column used to.
        supplier = po.get("vendor_name") or po.get("supplier_name") or "—"
        val = _total_of(po, "grand_total")
        po_vals.append(val)
        po_html += f"""
        <tr>
          <td><a href="{url_for('purchase.view_purchase', id=po.get('id'))}"><b>{P.esc(po.get('ref'))}</b></a></td>
          <td>{P.esc(po.get('date'))}</td>
          <td>{P.esc(supplier)}</td>
          <td style="text-align:right;">{_amt(val)}</td>
        </tr>
        """
    if attached_pos:
        po_html += _total_row(3, _sum_cell(po_vals))
    else:
        po_html = '<tr><td colspan="4" style="color:var(--muted);">No purchase orders attached.</td></tr>'

    # Charges
    attached_charges = [c for c in STORE.get("charges", {}).values() if c.get("project_id") == id]
    attached_charges.sort(key=lambda c: str(c.get("created_at") or ""), reverse=True)
    charge_html = ""
    charge_vals = []
    for c in attached_charges:
        # A charge stores no gross of its own; `charge.py`'s ledger adds the two
        # stored figures the same way, so this is that one path, not a second.
        gross = float(c.get("taxable_amount") or 0.0) + float(c.get("gst_amount") or 0.0)
        charge_vals.append(gross)
        charge_html += f"""
        <tr>
          <td>{P.esc(c.get('date'))}</td>
          <td><a href="{url_for('charge.edit_charge', id=c.get('id'))}"><b>{P.esc(c.get('person'))}</b></a></td>
          <td>{P.esc(c.get('head'))}</td>
          <td>{P.esc(c.get('description'))}</td>
          <td style="text-align:right;">{_amt(gross)}</td>
        </tr>
        """
    if attached_charges:
        charge_html += _total_row(4, _sum_cell(charge_vals))
    else:
        charge_html = '<tr><td colspan="5" style="color:var(--muted);">No employee charges attached.</td></tr>'

    # ── Eligible BOQs for attachment ──────────────────────────────────────────
    # BOQs not currently attached to this project. We list those with NO project attached, 
    # as moving a BOQ from one project to another usually splits P&Ls and requires care.
    eligible_boqs = [b for b in STORE.get("boqs", {}).values() if not b.get("project_id")]
    eligible_boqs.sort(key=lambda b: (str(b.get("date") or ""), str(b.get("ref") or "")), reverse=True)
    
    boq_opts = '<option value="">-- Select an unattached BOQ --</option>'
    for b in eligible_boqs:
        boq_opts += f'<option value="{b.get("id")}">{P.esc(b.get("ref"))} - {P.esc(b.get("account_name"))}</option>'

    # ── The site: the snapshot, the link, and where they disagree ────────────
    #
    # ⚠ **This page reads `site_address` exactly as it always did.** That field
    #   is now the label SNAPSHOT rather than free text, which is the whole
    #   point of the shape: existing records render identically and this block
    #   changes nothing about the figure above.
    #
    # ⚠ **The band REPORTS and never reconciles** — `ra.party_drift()`'s shape
    #   on `/ra/view`, deliberately rather than a second design, and DOMAIN.md
    #   §6's rule: surface it, name it, never silently correct it. Rewriting the
    #   snapshot here would restate history from a page that is supposed to be
    #   reading it.
    site_band = ""
    drift = PJ.site_drift(proj)
    if drift:
        snapshot, live = drift
        if live:
            site_band = (
                f'<div class="pm-drift"><span class="pm-drift-icon">&#9888;</span>'
                f'<span><b>This project\'s site was recorded as '
                f'&ldquo;{P.esc(snapshot) or "(blank)"}&rdquo;, and the address '
                f'book now reads &ldquo;{P.esc(live)}&rdquo;.</b> The address '
                f'has been edited since. The figure above is the one stored on '
                f'this project and is deliberately <b>not</b> restated &mdash; '
                f're-save the project to take the new label.</span></div>')
        else:
            site_band = (
                f'<div class="pm-drift"><span class="pm-drift-icon">&#9888;</span>'
                f'<span><b>This project points at an address that is no longer '
                f'in the book.</b> It still shows the label it was saved with, '
                f'&ldquo;{P.esc(snapshot) or "(blank)"}&rdquo;. Re-pick the '
                f'site on <a href="{url_for("project.edit_project", id=id)}">'
                f'Edit Project</a>.</span></div>')
    elif PJ.is_legacy_site(proj):
        site_band = (
            f'<div class="pm-drift"><span class="pm-drift-icon">&#9888;</span>'
            f'<span><b>This project\'s site is free text from before the '
            f'address book.</b> It has been left exactly as recorded and '
            f'nothing has been guessed at, so it does not join to anything. '
            f'Map it on <a href="{url_for("project.edit_project", id=id)}">'
            f'Edit Project</a>.</span></div>')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{B.page_title(proj.get('name', 'Project'))}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}
  {QUOTATION_STYLES}
  <style>
    .proj-meta {{ display:flex; gap:2rem; flex-wrap:wrap; margin-bottom:2rem; padding:1.25rem; background:#fff; border:1px solid var(--border); border-radius:8px; }}
    .pm-item {{ display:flex; flex-direction:column; gap:0.25rem; }}
    .pm-lbl {{ font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--muted); font-weight:700; }}
    .pm-val {{ font-size:1.05rem; font-weight:700; color:var(--navy); }}
    /* The amber divergence band. `ra.party_drift()`'s `.form-hint` on
       /ra/view is the shape; this is that shape in this page's own metrics. */
    .pm-drift {{ display:flex; gap:.6rem; align-items:flex-start;
                 border:1px solid #fde68a; background:#fffbeb; border-radius:8px;
                 padding:.75rem 1rem; margin-bottom:1.25rem;
                 font-size:.83rem; line-height:1.6; }}
    .pm-drift-icon {{ color:#b45309; font-size:1rem; line-height:1.3; }}
    .pm-drift a {{ color:#1d4ed8; }}

    .panel {{ background:#fff; border:1px solid var(--border); border-radius:8px; padding:1.25rem; margin-bottom:2rem; }}
    .panel-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; padding-bottom:0.75rem; border-bottom:1px solid var(--border); }}
    .panel-head h2 {{ margin:0; font-size:1.1rem; color:var(--navy); }}
    
    table.data {{ width:100%; border-collapse:collapse; font-size:0.9rem; }}
    table.data th, table.data td {{ text-align:left; padding:0.6rem 0.5rem; border-bottom:1px solid var(--border); }}
    table.data th {{ font-size:0.75rem; text-transform:uppercase; color:var(--muted); font-weight:700; background:var(--surface); }}
    table.data tr:last-child td {{ border-bottom:none; }}
    table.data tr.total-row td {{ font-weight:700; color:var(--navy); background:var(--surface); border-top:2px solid var(--border); }}
  </style>
</head>
<body>
  {_nav()}
  <main style="max-width:1100px; margin:0 auto; padding:1rem 1.25rem;">
    <div class="page-top">
      <h1>Project <span>{P.esc(proj.get('name'))}</span></h1>
      <div style="display:flex;gap:0.75rem;">
        <a href="{url_for('project.edit_project', id=id)}" class="btn btn-ghost">Edit Project</a>
        <a href="{url_for('project.list_projects')}" class="btn btn-ghost">All Projects</a>
      </div>
    </div>
    
    {_alert(msg, msg_type)}
    {site_band}

    <div class="proj-meta">
      <div class="pm-item">
        <span class="pm-lbl">Client</span>
        <span class="pm-val">{P.esc(proj.get('client')) or '—'}</span>
      </div>
      <div class="pm-item">
        <span class="pm-lbl">Site Address</span>
        <span class="pm-val">{P.esc(proj.get('site_address')) or '—'}</span>
      </div>
      <div class="pm-item">
        <span class="pm-lbl">Notes</span>
        <span class="pm-val">{P.esc(proj.get('notes')) or '—'}</span>
      </div>
    </div>

    <!-- BOQs Panel -->
    <div class="panel">
      <div class="panel-head">
        <h2>Bills of Quantities</h2>
      </div>
      
      <!-- Add BOQ Control -->
      <div style="background:var(--surface); padding:1rem; border-radius:6px; margin-bottom:1.5rem; display:flex; flex-wrap:wrap; gap:1.5rem; align-items:flex-end;">
        <div>
          <p style="margin:0 0 0.5rem 0; font-weight:600; font-size:0.9rem;">Create New</p>
          <a href="{url_for('boq.create_boq', project_id=id)}" class="btn">Raise new BOQ</a>
        </div>
        <div style="border-left:1px solid var(--border); padding-left:1.5rem;">
          <p style="margin:0 0 0.5rem 0; font-weight:600; font-size:0.9rem;">Attach Existing (Attaches entire revision chain)</p>
          <form method="POST" action="{url_for('projectview.view_project', id=id)}" style="display:flex; gap:0.5rem;">
            <input type="hidden" name="action" value="attach_boq">
            <select name="boq_id" class="form-control" style="min-width:250px;" required>
              {boq_opts}
            </select>
            <button type="submit" class="btn btn-ghost">Attach</button>
          </form>
        </div>
      </div>
      
      <table class="data">
        <thead>
          <tr>
            <th>Ref</th>
            <th>Date</th>
            <th>Revision</th>
            <th>Billed To</th>
            <th style="text-align:right;">BOQ Value</th>
          </tr>
        </thead>
        <tbody>
          {boq_html}
        </tbody>
      </table>
    </div>

    <!-- Proformas Panel -->
    <div class="panel">
      <div class="panel-head">
        <h2>Proforma Invoices</h2>
        <span style="font-size:0.8rem;color:var(--muted);">Proformas are tagged by hand on creation</span>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th>Ref</th>
            <th>Date</th>
            <th>Billed To</th>
            <th style="text-align:right;">PI Total</th>
          </tr>
        </thead>
        <tbody>
          {pi_html}
        </tbody>
      </table>
    </div>

    <!-- Tax Invoices Panel -->
    <div class="panel">
      <div class="panel-head">
        <h2>Tax Invoices</h2>
        <span style="font-size:0.8rem;color:var(--muted);">Tax invoices inherit their project from their proforma</span>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th>Ref</th>
            <th>Date</th>
            <th>Billed To</th>
            <th style="text-align:right;">TI Total</th>
          </tr>
        </thead>
        <tbody>
          {ti_html}
        </tbody>
      </table>
    </div>

    <!-- Purchase Orders Panel -->
    <div class="panel">
      <div class="panel-head">
        <h2>Purchase Orders</h2>
        <span style="font-size:0.8rem;color:var(--muted);">Purchase orders are tagged by hand on creation</span>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th>Ref</th>
            <th>Date</th>
            <th>Supplier</th>
            <th style="text-align:right;">PO Total</th>
          </tr>
        </thead>
        <tbody>
          {po_html}
        </tbody>
      </table>
    </div>

    <!-- Charges Panel -->
    <div class="panel">
      <div class="panel-head">
        <!-- ⚠ Labelled "Employee & Misc Charges" until 29 August 2026 — the
             THIRD site carrying that wording, outside the two corrected with
             charge.py's own title. A real employee master now exists
             (employee.py, CC-2 C4), and this ledger has never had an employee
             record behind it: "Person" below is a free-text field somebody
             types. The module is NOT renamed — charge.py, /charge and
             charge.* all stay. The label is what was wrong. PROGRESS.md §6-E. -->
        <h2>Expenses & Charges</h2>
        <span style="font-size:0.8rem;color:var(--muted);">Expenses tagged to this project</span>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th>Date</th>
            <th>Person</th>
            <th>Head</th>
            <th>Description</th>
            <th style="text-align:right;">Gross Amount</th>
          </tr>
        </thead>
        <tbody>
          {charge_html}
        </tbody>
      </table>
    </div>

  </main>
</body>
</html>"""
    return _page(html)
