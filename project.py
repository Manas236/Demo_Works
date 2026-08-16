"""
project.py — The project entity
================================
Blueprint  : project_bp
Mounted at : /projects  (registered in app.py)

Routes
------
  GET       /projects/                — register, newest first
  GET,POST  /projects/create          — create a new project
  GET,POST  /projects/edit/<id>       — edit an existing project
  GET,POST  /projects/delete/<id>     — confirm-then-destroy (9d060ee's shape)

CLIENT_CHANGES.md items 9 and 10.  A project is the commercial engagement BOQs
are grouped under.  It has a stable id chosen once by a human, not a string
re-derived on every page load — which is why grouping on the existing
`project_name` field was rejected (see the prompt that built this module).

Two things it is not
--------------------
**It is not a P&L.**  Revenue and cost are undefined for this business, and the
definitions are the client's and their CA's.  This module groups BOQs, computes
nothing, and shows no money.

**It is not a display label.**  `project_name` stays on the BOQ as a display
field, but the grouping key is `project_id` — a UUID minted here.

Import direction — LEAF
-----------------------
    project.py ──► dashboard.py  BASE_STYLES / _nav
    project.py ──► pipeline.py   esc / norm_name
    project.py ──► store         the shared STORE dict
    project.py ──► branding      company strings, page title

Nothing imports this module at module level EXCEPT boq.py. boq.py imports
project.py to use its API rather than coupling directly to STORE["projects"].

project.py does NOT import: boq, challan, purchase, po_draft, invoice, ra,
receipt, quotation, product, docsheet, boqpick.  That list is asserted in
tests/test_import_directions.py.
"""

import uuid
from datetime import datetime

from flask import Blueprint, redirect, request, url_for

import branding as B
import pipeline as P
from store import STORE

from dashboard import BASE_STYLES, _nav

project_bp = Blueprint("project", __name__, url_prefix="/projects")


# =============================================================================
# HELPERS
# =============================================================================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _page(html: str) -> str:
    """Return finished HTML unchanged — no Jinja re-parse (ABOUT.md §7.9d)."""
    return html


def _project_by_norm(norm: str):
    """Find an existing project by normalised name, or None."""
    for pid, proj in STORE["projects"].items():
        if proj.get("norm_name") == norm:
            return pid, proj
    return None, None


def boqs_for_project(project_id: str) -> list:
    """Every BOQ that carries this project_id."""
    return [b for b in STORE.get("boqs", {}).values()
            if str(b.get("project_id", "")) == project_id]


def attached_boq_count(project_id: str) -> int:
    """How many BOQs are attached to this project."""
    return sum(1 for b in STORE.get("boqs", {}).values()
               if str(b.get("project_id", "")) == project_id)


# =============================================================================
# ROUTES
# =============================================================================

@project_bp.route("/")
def list_projects():
    """Projects register, newest first."""
    msg     = request.args.get("msg", "")
    msg_type = request.args.get("type", "success")

    projects = sorted(STORE["projects"].values(),
                       key=lambda p: p.get("created_at", ""), reverse=True)

    rows = ""
    for p in projects:
        pid = p["id"]
        n_boqs = attached_boq_count(pid)
        rows += f"""
        <tr>
          <td><a href="{url_for('projectview.view_project', id=pid)}">{P.esc(p.get('name'))}</a></td>
          <td>{P.esc(p.get('client') or '') or '&mdash;'}</td>
          <td>{P.esc(p.get('site_address') or '') or '&mdash;'}</td>
          <td>{n_boqs}</td>
          <td class="td-acts">
            <a href="{url_for('project.edit_project', id=pid)}" class="btn btn-sm">Edit</a>
            <a href="{url_for('project.delete_project', id=pid)}" class="btn btn-sm btn-ghost">Delete</a>
          </td>
        </tr>"""

    alert = ""
    if msg:
        alert = f'<div class="alert alert-{P.esc(msg_type)}">{P.esc(msg)}</div>'

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Projects")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
      <style>
        .proj-head {{ display:flex; justify-content:space-between; align-items:center;
                      margin:1.5rem 0 1rem; }}
        .proj-tbl {{ width:100%; border-collapse:collapse; }}
        .proj-tbl th, .proj-tbl td {{ padding:.55rem .7rem; text-align:left;
                                      border-bottom:1px solid #e2e2e2; }}
        .proj-tbl th {{ font-size:.82rem; text-transform:uppercase; letter-spacing:.04em;
                        color:#666; }}
        .td-acts {{ white-space:nowrap; }}
        .btn-sm {{ font-size:.8rem; padding:.25rem .55rem; }}
      </style>
    </head>
    <body>
      {_nav()}
      <main style="max-width:900px; margin:0 auto; padding:1rem 1.25rem;">
        {alert}
        <div class="proj-head">
          <h1>Projects</h1>
          <a href="{url_for('project.create_project')}" class="btn">+ New Project</a>
        </div>

        <table class="proj-tbl">
          <thead>
            <tr>
              <th>Project</th><th>Client</th><th>Site</th><th>BOQs</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows if rows else '<tr><td colspan="5" style="text-align:center; color:#999; padding:2rem;">No projects yet.</td></tr>'}
          </tbody>
        </table>
      </main>
    </body>
    </html>
    """
    return _page(html)




@project_bp.route("/create", methods=["GET", "POST"])
def create_project():
    """Create a new project."""
    error = ""

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            error = "A project needs a name."

        if not error:
            norm = P.norm_name(name)
            existing_pid, existing = _project_by_norm(norm)
            if existing:
                error = (f"A project with a similar name already exists: "
                         f"'{P.esc(existing.get('name'))}'. "
                         f"Edit it instead, or use a distinct name.")

        if not error:
            pid = str(uuid.uuid4())
            now = _now()
            STORE["projects"][pid] = {
                "id":           pid,
                "name":         name,
                "norm_name":    P.norm_name(name),
                "client":       (request.form.get("client") or "").strip(),
                "site_address": (request.form.get("site_address") or "").strip(),
                "notes":        (request.form.get("notes") or "").strip(),
                "created_at":   now,
                "updated_at":   now,
            }
            return redirect(url_for("project.list_projects",
                                    msg=f"Project '{P.esc(name)}' created.",
                                    type="success"))

    # GET or rejected POST
    _v = lambda k: P.esc(request.form.get(k, "")) if request.method == "POST" else ""

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("New Project")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
      <style>
        .pf {{ max-width:600px; margin:1.5rem auto; }}
        .pf label {{ display:block; margin-top:1rem; font-weight:600; font-size:.88rem; }}
        .pf input, .pf textarea {{ width:100%; padding:.45rem .6rem; font-size:.92rem;
                                   border:1px solid #ccc; border-radius:4px; }}
        .pf textarea {{ min-height:4rem; resize:vertical; }}
        .pf .acts {{ margin-top:1.25rem; }}
      </style>
    </head>
    <body>
      {_nav()}
      <main class="pf">
        <h1>New Project</h1>
        {'<div class="alert alert-error">' + P.esc(error) + '</div>' if error else ''}
        <form method="POST">
          <label for="name">Project Name *</label>
          <input type="text" id="name" name="name" value="{_v('name')}"
                 placeholder="Sify Bangalore" required/>

          <label for="client">Client</label>
          <input type="text" id="client" name="client" value="{_v('client')}"
                 placeholder="Prudent Teqtis Pvt Ltd"/>

          <label for="site_address">Site Address</label>
          <input type="text" id="site_address" name="site_address" value="{_v('site_address')}"
                 placeholder="Bangalore, Karnataka"/>

          <label for="notes">Notes</label>
          <textarea id="notes" name="notes" placeholder="Optional">{_v('notes')}</textarea>

          <div class="acts">
            <button type="submit" class="btn">Create</button>
            <a href="{url_for('project.list_projects')}" class="btn btn-ghost">Cancel</a>
          </div>
        </form>
      </main>
    </body>
    </html>
    """
    return _page(html)


@project_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_project(id: str):
    """Edit an existing project."""
    proj = STORE["projects"].get(id)
    if not proj:
        return redirect(url_for("project.list_projects",
                                msg="Project not found.", type="error"))

    error = ""

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            error = "A project needs a name."

        if not error:
            norm = P.norm_name(name)
            # Allow the same project to keep its name
            existing_pid, existing = _project_by_norm(norm)
            if existing and existing_pid != id:
                error = (f"A project with a similar name already exists: "
                         f"'{P.esc(existing.get('name'))}'. "
                         f"Use a distinct name.")

        if not error:
            proj["name"]         = name
            proj["norm_name"]    = P.norm_name(name)
            proj["client"]       = (request.form.get("client") or "").strip()
            proj["site_address"] = (request.form.get("site_address") or "").strip()
            proj["notes"]        = (request.form.get("notes") or "").strip()
            proj["updated_at"]   = _now()
            return redirect(url_for("project.list_projects",
                                    msg=f"Project '{P.esc(name)}' updated.",
                                    type="success"))

    # GET or rejected POST
    def _v(k):
        if request.method == "POST":
            return P.esc(request.form.get(k, ""))
        return P.esc(proj.get(k, ""))

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Edit Project")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
      <style>
        .pf {{ max-width:600px; margin:1.5rem auto; }}
        .pf label {{ display:block; margin-top:1rem; font-weight:600; font-size:.88rem; }}
        .pf input, .pf textarea {{ width:100%; padding:.45rem .6rem; font-size:.92rem;
                                   border:1px solid #ccc; border-radius:4px; }}
        .pf textarea {{ min-height:4rem; resize:vertical; }}
        .pf .acts {{ margin-top:1.25rem; }}
      </style>
    </head>
    <body>
      {_nav()}
      <main class="pf">
        <h1>Edit Project</h1>
        {'<div class="alert alert-error">' + P.esc(error) + '</div>' if error else ''}
        <form method="POST">
          <label for="name">Project Name *</label>
          <input type="text" id="name" name="name" value="{_v('name')}" required/>

          <label for="client">Client</label>
          <input type="text" id="client" name="client" value="{_v('client')}"/>

          <label for="site_address">Site Address</label>
          <input type="text" id="site_address" name="site_address" value="{_v('site_address')}"/>

          <label for="notes">Notes</label>
          <textarea id="notes" name="notes">{_v('notes')}</textarea>

          <div class="acts">
            <button type="submit" class="btn">Save</button>
            <a href="{url_for('project.list_projects')}" class="btn btn-ghost">Cancel</a>
          </div>
        </form>
      </main>
    </body>
    </html>
    """
    return _page(html)


@project_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_project(id: str):
    """
    GET renders a confirmation page, POST destroys.

    9d060ee's shape: the GET mutates nothing, the POST is the only path that
    writes. A browser confirm() is not a guard (ABOUT.md §7.9f).

    Refused with a message when any BOQ is attached.
    """
    proj = STORE["projects"].get(id)
    if not proj:
        return redirect(url_for("project.list_projects",
                                msg="Project not found.", type="error"))

    n_boqs = attached_boq_count(id)

    if request.method == "POST":
        if n_boqs > 0:
            return redirect(url_for("project.list_projects",
                                    msg=f"Cannot delete '{P.esc(proj.get('name'))}' — "
                                        f"{n_boqs} BOQ(s) are attached to it.",
                                    type="error"))
        name = proj.get("name", "")
        del STORE["projects"][id]
        return redirect(url_for("project.list_projects",
                                msg=f"Project '{P.esc(name)}' deleted.",
                                type="success"))

    # GET — confirmation page. Reads only, writes nothing.
    if n_boqs > 0:
        refusal = (f'<div class="alert alert-error">Cannot delete — '
                   f'{n_boqs} BOQ(s) are attached to this project. '
                   f'Reassign or remove them first.</div>')
        btn = ""
    else:
        refusal = ""
        btn = '<button type="submit" class="btn" style="background:#c0392b;">Delete</button>'

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{B.page_title("Delete Project")}</title>
      {B.HEAD_ICON}
      {BASE_STYLES}
    </head>
    <body>
      {_nav()}
      <main style="max-width:600px; margin:1.5rem auto; padding:1rem 1.25rem;">
        <h1>Delete Project</h1>
        {refusal}
        <p>Are you sure you want to delete <strong>{P.esc(proj.get('name'))}</strong>?</p>
        <form method="POST" style="margin-top:1rem;">
          {btn}
          <a href="{url_for('project.list_projects')}" class="btn btn-ghost">Cancel</a>
        </form>
      </main>
    </body>
    </html>
    """
    return _page(html)
"""project.py"""
