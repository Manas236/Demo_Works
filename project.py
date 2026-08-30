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

The site comes from the ADDRESS BOOK
------------------------------------
⚠ **`site_address` was free text somebody typed until 30 August 2026 (fourth
pass), and that is why this database spells one place two ways** — *"Banglore,
Karnataka"* on two projects and *"Bangalore, Karnataka"* on a third. A project's
site is a **join key**, and free text cannot join.

The record now carries **two** fields and they are not duplicates:

    site_address_id   the address-book link  — the join
    site_address      the address LABEL, snapshotted at save — the display

**Why the snapshot, and not a pure reference.** Every current reader — the SITE
column on the register below, `projectview.py`, anything printing a project —
already reads `site_address`. Making the existing field the snapshot means those
readers do not change and existing records keep rendering exactly as they do
today: *"existing records unharmed"* is true **by construction** rather than by
migration. It is also the house pattern — `charge.py` stores `project_id` **and**
snapshots `project_name`.

**Where that falls short, and what is built for it.** Two copies of one string
can disagree after an address is edited. ⚠ **Nothing here silently reconciles
them.** `site_drift()` below reports the disagreement and `/projects/view/<id>`
raises an amber band over it — `ra.party_drift()`'s shape on `/ra/view`, and
DOMAIN.md §6's rule: surface it, name it, never silently correct it.

⚠ **This is NOT C6 and does not unblock it.** C6 is BLOCKED on CC-2's Open
question 4. This closes one of the two shortfalls C6 would have to close and
touches neither the other one nor `projectview.py`'s margin prohibition.

Import direction — a LEAF that now reaches the book
---------------------------------------------------
    project.py ──► dashboard.py  BASE_STYLES / _nav
    project.py ──► pipeline.py   esc / norm_name
    project.py ──► store         the shared STORE dict
    project.py ──► branding      company strings, page title
    project.py ──► address.py    the SITE picker and SITE_TYPES  (30 Aug 2026)

⚠ **`address.py` does NOT import back**, and cannot: it is imported by five
other modules already. It reads `STORE["projects"]` directly for
`references_of()` — the one-way trick, exactly as `boq.py` reads
`STORE["ra_bills"]`.

⚠ **`SITE_TYPES` is read from `address.py`, never redefined here.** Two pickers
that can disagree about what counts as a site is the defect this arrow exists to
prevent; `employee.py` reads the same tuple from the same place.

boq.py imports project.py to use its API rather than coupling directly to
STORE["projects"], and projectview.py imports it for `site_drift()` — the drift
belongs to the module that writes both copies, for the reason `party_drift()`
lives in `ra.py`.

project.py does NOT import: boq, challan, purchase, po_draft, invoice, ra,
receipt, quotation, product, docsheet, boqpick.  That list is asserted in
tests/test_import_directions.py.
"""

import uuid
from datetime import datetime

from flask import Blueprint, redirect, request, url_for

import address as AD
import branding as B
import pipeline as P
from store import STORE

from dashboard import BASE_STYLES, _nav

project_bp = Blueprint("project", __name__, url_prefix="/projects")

# The link. `site_address` beside it is the label snapshot — see the docstring.
SITE_ADDRESS_ID_FIELD = "site_address_id"


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
# THE SITE — the link, the snapshot, and what to do when they disagree
# =============================================================================

def site_label_of(address_id) -> str:
    """
    The address's label as the book holds it **now**, or `""` when the id names
    nothing.

    ⚠ **An ARCHIVED address still resolves here.** Archiving takes an address
    out of the pickers; it does not take it away from the records that already
    name it, and a project whose site was archived must go on saying where the
    work is.
    """
    a = (STORE.get("addresses") or {}).get(str(address_id or "")) or {}
    return str(a.get("label") or "")


def is_legacy_site(proj) -> bool:
    """
    Whether this project's site is a free-text string nothing has mapped.

    ⚠ **Read from the SHAPE, not from a mark**, and that is the one place this
    differs from `employee.is_unmapped_site()`. The muster carries an explicit
    `site_source` because its backfill had to distinguish "matched exactly" from
    "left alone"; here there is nothing to distinguish. A project either has an
    id or it does not, and one with a string and no id is unambiguously a record
    written before the picker. No third state exists and none is invented.
    """
    proj = proj or {}
    return (bool(str(proj.get("site_address") or "").strip())
            and not str(proj.get(SITE_ADDRESS_ID_FIELD) or "").strip())


def others_on_site(address_id, except_id: str = "") -> list:
    """
    Every OTHER project whose site is this address, name order.

    ⚠ **This is the evidence behind the ambiguity note on `/projects/view/<id>`,
    and the count is the whole point of it.** The client has said *one project =
    one site*; he has **not** said one site = one project, and this database
    disproves the converse on its own: `'Bangalore, Karnataka'` carries several.
    So anything read off a site — a delivery, an expense, a day's labour —
    belongs to **all** of the projects on that site as far as the data can say,
    and to exactly one of them in reality. Naming which is C6, BLOCKED on CC-2's
    Open question 4.

    ⚠ **A BLANK id returns nothing**, never "every project with no site". Two
    records that share only an empty field share nothing, and `""` matching `""`
    is how the unlinked projects would come back as each other's siblings.

    Lives here rather than in `projectview.py` because a question about the
    project collection belongs to the module that owns it —
    `attached_boq_count()`'s precedent two functions up, and the reason
    `site_drift()` is here and not on the page that draws its band.
    """
    aid = str(address_id or "").strip()
    if not aid:
        return []
    return sorted((p for p in (STORE.get("projects") or {}).values()
                   if str(p.get(SITE_ADDRESS_ID_FIELD) or "").strip() == aid
                   and p.get("id") != except_id),
                  key=lambda p: str(p.get("name") or "").lower())


def site_drift(proj):
    """
    Where the snapshot and the live address have come apart, or `None`.

    Returns `(snapshot, live)`. `live` is `""` when the id names nothing at all,
    which is the dangling case rather than the renamed one, and the band says
    which.

    ⚠ **This REPORTS and never reconciles.** `ra.party_drift()`'s shape and
    exactly its reason: a stored figure is what it is, and correcting it behind
    somebody's back is worse than showing them two numbers and saying which is
    which. DOMAIN.md §6 — surface it, name it, never silently correct it.

    A project with no id has no drift to report: there is nothing to compare the
    snapshot against, and `is_legacy_site()` is the state that describes it.
    """
    proj = proj or {}
    aid = str(proj.get(SITE_ADDRESS_ID_FIELD) or "").strip()
    if not aid:
        return None
    snapshot = str(proj.get("site_address") or "").strip()
    live = site_label_of(aid)
    return None if live == snapshot else (snapshot, live)


def _site_from(form, proj=None) -> tuple:
    """
    `(fields, error)` — the two site keys a project record carries, or why not.

    ⚠ **The picker is the ONLY path. There is no free-text fallback**, and that
    is a deliberate departure from `challan.py`'s consignee, which keeps one. The
    tie-breaker is that a project's site is a **join key**: a site store that
    exists for four months is not worth an address-book entry, but a project's
    site has to be the same object the muster and the register are talking
    about, and free text cannot join.

    ⚠ **A LEGACY project must be picked before it can be saved.** Its string is
    left exactly as it stands until then — the form does not rewrite it, and
    `tools/backfill_project_sites.py` is what maps it in bulk. Saving a legacy
    record with the picker untouched would write the id-less shape back
    permanently, one edit at a time.

    An empty pick on a project that is **not** legacy clears both keys, which is
    how a site is deliberately removed.
    """
    site_id = (form.get(SITE_ADDRESS_ID_FIELD) or "").strip()[:64]

    if not site_id:
        if proj is not None and is_legacy_site(proj):
            return {}, ("This project's site is a free-text string from before "
                        "the address book: "
                        f"'{str(proj.get('site_address') or '').strip()}'. "
                        "Choose the matching address to map it — or add it to "
                        "the address book first. It has been left exactly as "
                        "recorded rather than guessed at.")
        return {SITE_ADDRESS_ID_FIELD: "", "site_address": ""}, ""

    addr = (STORE.get("addresses") or {}).get(site_id)
    if not addr:
        return {}, "That site is no longer in the address book."
    if addr.get("type") not in AD.SITE_TYPES:
        # The picker offers `SITE_TYPES` only, so this is a hand-made POST.
        # Refused rather than stored: a vendor is somebody we buy from, not a
        # place work happens.
        return {}, ("That address is not a site or an office, so it cannot be "
                    "a project's site.")

    # ⚠ The label is SNAPSHOTTED, not looked up on every render. See the module
    #   docstring: every existing reader goes on reading `site_address`.
    return {SITE_ADDRESS_ID_FIELD: site_id,
            "site_address": str(addr.get("label") or "").strip()}, ""


def _site_field(selected: str = "", proj=None) -> str:
    """
    The site form group — one widget, so two forms cannot offer two.

    Carries three things the picker on its own cannot survive without:

    * ⚠ **an "Add a new address" link.** Without it a user standing in front of
      a project whose site is not in the book has **no move at all**. It is
      required, not decoration.
    * ⚠ **the empty-book case**, said in words rather than as a `<select>` with
      one placeholder in it. `picker_options()` no longer seeds, so an empty
      book is now a state a form can genuinely open in.
    * **the legacy string**, shown and marked, so somebody mapping a record can
      see what they are mapping it to.
    """
    add_url = url_for("address.add_address")

    legacy = ""
    if proj is not None and is_legacy_site(proj):
        legacy = (f'<div class="pf-legacy"><b>Recorded as free text: '
                  f'&ldquo;{P.esc(proj.get("site_address"))}&rdquo;</b> '
                  f'&mdash; from before the site came from the address book. '
                  f'It has been left exactly as it stands and nothing has been '
                  f'guessed at. Choose the matching address to map it; saving '
                  f'needs a pick.</div>')

    if not AD.has_options(AD.SITE_TYPES):
        return (f'<label>Site Address</label>{legacy}'
                f'<div class="pf-empty">No sites in the address book &mdash; '
                f'<a href="{add_url}">add one</a>. A project\'s site is a link '
                f'to the book, not typed text.</div>')

    opts = AD.picker_options("— choose a site from the address book —",
                             only_types=AD.SITE_TYPES, selected=selected)
    return (f'<label for="{SITE_ADDRESS_ID_FIELD}">Site Address</label>{legacy}'
            f'<select id="{SITE_ADDRESS_ID_FIELD}" '
            f'name="{SITE_ADDRESS_ID_FIELD}">{opts}</select>'
            f'<div class="pf-hint">Not in the list? '
            f'<a href="{add_url}">Add a new address</a> &mdash; give it the '
            f'type <b>Project Site</b>.</div>')


PROJECT_FORM_STYLES = """
        .pf-hint {{ font-size:.78rem; color:#666; margin-top:.35rem; }}
        .pf-hint a {{ color:#1d4ed8; }}
        .pf-legacy {{ border:1px solid #fde68a; background:#fffbeb;
                      border-radius:8px; padding:.6rem .8rem; margin:.4rem 0;
                      font-size:.79rem; line-height:1.55; font-weight:400; }}
        .pf-empty {{ border:1px dashed #ccc; background:#fafafa;
                     border-radius:8px; padding:.6rem .8rem; margin:.4rem 0;
                     font-size:.79rem; line-height:1.55; font-weight:400; }}
"""


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

        site_fields = {SITE_ADDRESS_ID_FIELD: "", "site_address": ""}
        if not error:
            site_fields, site_error = _site_from(request.form)
            error = error or site_error

        if not error:
            pid = str(uuid.uuid4())
            now = _now()
            STORE["projects"][pid] = {
                "id":           pid,
                "name":         name,
                "norm_name":    P.norm_name(name),
                "client":       (request.form.get("client") or "").strip(),
                # Two keys, not one. `site_address` is the LABEL SNAPSHOT
                # written from the chosen address — see the module docstring.
                **site_fields,
                "notes":        (request.form.get("notes") or "").strip(),
                "created_at":   now,
                "updated_at":   now,
            }
            return redirect(url_for("project.list_projects",
                                    msg=f"Project '{P.esc(name)}' created.",
                                    type="success"))

    # GET or rejected POST
    _v = lambda k: P.esc(request.form.get(k, "")) if request.method == "POST" else ""
    site_field = _site_field(
        selected=(request.form.get(SITE_ADDRESS_ID_FIELD, "")
                  if request.method == "POST" else ""))

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
        .pf input, .pf textarea, .pf select {{ width:100%; padding:.45rem .6rem; font-size:.92rem;
                                   border:1px solid #ccc; border-radius:4px; }}
        .pf textarea {{ min-height:4rem; resize:vertical; }}
        .pf .acts {{ margin-top:1.25rem; }}
{PROJECT_FORM_STYLES}
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

          {site_field}

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

        site_fields = {}
        if not error:
            site_fields, site_error = _site_from(request.form, proj)
            error = error or site_error

        if not error:
            proj["name"]         = name
            proj["norm_name"]    = P.norm_name(name)
            proj["client"]       = (request.form.get("client") or "").strip()
            # ⚠ Both keys move together or neither does. A form that wrote the
            #   id and left the snapshot would manufacture the exact drift
            #   `site_drift()` exists to report.
            proj.update(site_fields)
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

    site_field = _site_field(
        selected=(request.form.get(SITE_ADDRESS_ID_FIELD, "")
                  if request.method == "POST"
                  else str(proj.get(SITE_ADDRESS_ID_FIELD) or "")),
        proj=proj)

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
        .pf input, .pf textarea, .pf select {{ width:100%; padding:.45rem .6rem; font-size:.92rem;
                                   border:1px solid #ccc; border-radius:4px; }}
        .pf textarea {{ min-height:4rem; resize:vertical; }}
        .pf .acts {{ margin-top:1.25rem; }}
{PROJECT_FORM_STYLES}
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

          {site_field}

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
