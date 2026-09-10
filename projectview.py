"""
projectview.py — Project Detail Page
====================================
Blueprint  : projectview_bp
Mounted at : /projects (registered in app.py)

This module replaces the dummy view in project.py.
It displays project metadata and gathers documents attached to the project.

⚠ **One panel on this page shows its rows in TWO groups, and the difference
between them is the first thing to understand about it.** *Site Labour* is that
panel, and it renders:

    1. Booked to this project    r["project_id"] == id   somebody CHOSE this
    2. At this site, unattributed  r["site_address_id"] == the project's site,
                                   and r["project_id"] is empty

Group 1 is the same mechanism as every other panel here — an id somebody picked,
exactly as a BOQ, a proforma, a purchase order and a charge carry one. **Group 2
is not**: those rows are matched through a third record, the address book, which
names no project at all, so where two projects share a site **both pages show
those same markings and the same money**. Each group carries a caption saying
which it is, they are summed **separately**, and nothing anywhere adds the two
together.

⚠ **The ambiguity note is conditional now and that is deliberate.** It appears
only where group 2 is non-empty **and** other projects share the site — the
conditions under which the double count is real. Where every marking is
attributed the ambiguity is resolved and the page says nothing, because a page
that goes on warning about a resolved ambiguity teaches its reader to ignore the
warning.

See `_site_labour()` and `_labour_group()` at the foot of this file.
CLIENT_CHANGES.md §0's **fifth** block of 30 August 2026 is the authority for
the section existing at all; its **sixth** block is the authority for the two
groups. ⚠ **Neither is CC-2 scope** and **C6 stays BLOCKED** on Open question 4:
attributing a day is not costing a project.

Each panel shows the documents' OWN values and adds that one column up. What
this page must never show is a figure that only exists by combining two panels
— no revenue total, no cost total, no margin, no profit, no net, no balance.
The page reads what the sell side billed and what the buy side committed side
by side; it does not do the subtraction, because the moment it does, the
project page becomes a P&L that nobody signed off on.
"""

from flask import Blueprint, redirect, request, url_for
import attendance as AT
import auth
import branding as B
import pipeline as P
import project as PJ
import settings as S
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


# =============================================================================
# SITE LABOUR — markings booked at this project's SITE
# =============================================================================
#
# ⚠ **NOT CC-2 SCOPE.** Authorised by the FIFTH override block of 30 August 2026
#   in CLIENT_CHANGES.md §0, recorded in PROGRESS.md §4c, and citable as neither
#   a delivered CC-2 item nor anything MG/SF/2026-02 covers.
#
# ⚠ **C6 IS STILL BLOCKED** on CC-2's Open question 4 — whether attendance wages
#   or the BOQ installation base rate is authoritative for labour cost. This
#   section answers it in no direction. It **presents markings**; it is not a
#   cost authority, and no figure it renders may be subtracted from anything.
#
# ⚠ **THE MECHANISM IS DIFFERENT FROM EVERY OTHER PANEL ON THIS PAGE, and that
#   is the whole reason the wording below is written the way it is.**
#
#     Expenses & Charges   c["project_id"] == id     somebody CHOSE this project
#     Site Labour, group 1 r["project_id"] == id     somebody CHOSE this project
#     Site Labour, group 2 r["site_address_id"]      nobody chose anything; the
#                            == proj["site_address_id"]   two records share a PLACE
#
#   ⚠ **The middle row is new on 30 August 2026 (sixth pass) and it is the fix.**
#   A marking now carries a `project_id` picked off a dropdown filtered to its
#   own site, so group 1 answers the same way a charge does. Group 2 is the
#   legacy shape — a marking written before the field, matched through the
#   address book — and a site can carry several projects, this database having
#   one address that carries four. Those rows appear on every one of those
#   projects' pages showing the same money, and a reader who adds them across
#   projects has counted one day's labour more than once. **Keeping the two
#   groups apart, and summing them apart, is what stops that.** It is not
#   decoration and the groups may not be merged to tidy the page up.

def _labour_note(proj, others, unattributed) -> str:
    """
    The line under the section heading. It has one job: say what these rows are.

    ⚠ **REWRITTEN 30 August 2026, sixth pass. It used to be true of every row on
    the page and is now true of only one of the two groups.** Its old lead was,
    verbatim:

        Attendance markings booked at <b>{site}</b> — this project's site. They
        are <b>not</b> tagged to this project: a marking records a person, a day
        and a <b>site</b>, and carries no project of any kind.

    The last clause stopped being true when a marking gained a `project_id`.
    **Group 1's rows now ARE tagged to this project**, by an id somebody picked
    off a filtered dropdown — the same mechanism *"Expenses tagged to this
    project"* one panel up describes. So the sentence moved: it is the caption
    on group **2**, where it is still exactly right, and group 1 gets a caption
    of its own that says the opposite.

    ⚠ **The ambiguity note has to EARN its place now, and this is where it is
    decided.** It appears only where `unattributed` is non-empty **and** other
    projects share the site: those are the conditions under which the same money
    really does appear on another project's page. Where every marking is
    attributed the ambiguity is **resolved**, and a page that goes on warning
    about a resolved ambiguity teaches its reader to ignore the warning.
    """
    site = P.esc(str(proj.get("site_address") or "")) or "this project's site"
    lead = (f'Attendance markings at <b>{site}</b> &mdash; this project&rsquo;s '
            f'site &mdash; in two groups: the ones <b>booked to this '
            f'project</b>, and the ones booked at the site that name no project '
            f'at all. <b>The two are never added together.</b>')

    # ⚠ Both conditions, and neither alone. Siblings with nothing unattributed
    #   is a resolved ambiguity; unattributed rows with no siblings is a gap in
    #   the data but not a double count, and the group's own caption says so.
    if not others or not unattributed:
        return lead

    names = ", ".join(
        f'<a href="{url_for("projectview.view_project", id=o.get("id"))}">'
        f'{P.esc(o.get("name")) or "(unnamed)"}</a>' for o in others)
    n = len(others)
    u = len(unattributed)
    return (
        f'{lead}'
        f'<div class="sl-ambig"><span class="sl-ambig-icon">&#9888;</span>'
        f'<span><b>{n} other project{"" if n == 1 else "s"} '
        f'{"is" if n == 1 else "are"} recorded at this same site: {names}.</b> '
        f'The <b>{u} unattributed marking{"" if u == 1 else "s"}</b> below '
        f'appear{"s" if u == 1 else ""} on {"that page" if n == 1 else "those pages"} '
        f'too, showing the same money. Which project '
        f'{"that day" if u == 1 else "those days"} of labour belongs to '
        f'<b>cannot be determined from this data</b> &mdash; nothing on '
        f'{"that marking" if u == 1 else "those markings"} names a project '
        f'&mdash; so nothing here attributes '
        f'{"it" if u == 1 else "them"} to one, and '
        f'{"that figure" if u == 1 else "those figures"} must not be added '
        f'together across projects. Attribute '
        f'{"it" if u == 1 else "them"} on the marking to make this note go '
        f'away.</span></div>')


def _site_labour(proj) -> str:
    """
    The Site Labour panel, or the empty state that explains why there is none.

    ⚠ **Reads `attendance.py` through its own accessors and never reaches into
    the collection.** `tests/test_attendance.py` asserts that only that module
    and the launcher do, and that guard is **not** weakened by this pass — it is
    still green, and it has to stay green. The markings arrive from
    `markings_at_site()`, the cells from `marking_cells()`, and the wage
    arithmetic never leaves the module that owns it. An import is a much
    narrower thing to have opened than a second reader of the raw dict: one
    module now consumes a published answer, and nothing outside `attendance.py`
    can still compute a wage.
    """
    # ── ⚠ B4's WALL, and it is the first thing checked ──────────────────────
    #
    # `/projects/view/<id>` is classified `project.view`, which **Sales Manager,
    # Purchase Manager and Accountant all hold**. `attendance.*` is granted to
    # Owner, Director and HR only, and that restriction is SPEC-TRACED to CC-2
    # **B4**: *"HR information is restricted from Sales, Purchase and
    # Accounts."* A day rate and a wage are that information in its plainest
    # form — it is why the whole muster is walled off.
    #
    # ⚠ **So rendering these rows under `project.view` alone would hand the
    #   three walled-off roles exactly the figures B4 keeps from them**, through
    #   a page they are entitled to read. The registry cannot express "this
    #   panel needs a second permission" — it is endpoint-level, ABOUT.md §7
    #   gap 24 — so this is a per-view check, the shape that gap prescribes and
    #   the same one the POST branch above already uses.
    #
    # ⚠ **It says the section exists and is withheld, rather than rendering
    #   nothing.** A panel that silently vanishes for some readers is a page
    #   that describes the project differently depending on who is looking,
    #   with nothing on screen saying so.
    if not auth.has_perm("attendance.view"):
        return ('<p class="sl-empty">Attendance detail for this site needs the '
                '<b>View attendance</b> permission '
                '(<code>attendance.view</code>), which your roles do not '
                'include. Wage information is restricted to Owner, Director '
                'and HR.</p>')

    aid = str(proj.get(PJ.SITE_ADDRESS_ID_FIELD) or "").strip()

    # ── Empty state 1: no site linked ───────────────────────────────────────
    # ⚠ Checked FIRST and separately from "no markings", because the two need
    #   different answers: this one has a fix and a link to it, and the other
    #   does not. `markings_at_site("")` also returns nothing, so a single
    #   combined branch would tell somebody with an unlinked project that
    #   nobody worked, which is a statement about the site rather than the data.
    if not aid:
        legacy = PJ.is_legacy_site(proj)
        why = ("Its site is free text from before the address book, so it "
               "joins to nothing." if legacy else "No site has been recorded.")
        return (
            f'<p class="sl-empty"><b>This project has no site linked.</b> {why} '
            f'Attendance is recorded against an address-book site, so there is '
            f'nothing to match on. Link one on '
            f'<a href="{url_for("project.edit_project", id=proj.get("id"))}">'
            f'Edit Project</a>.</p>')

    # ⚠ **TWO GROUPS, and they are read from the module rather than split
    #   here.** `markings_for_project()` answers by the id somebody picked;
    #   `unattributed_at_site()` answers by the site, for the rows that name no
    #   project. Splitting one list locally would put a second definition of
    #   "attributed" on this page, which is the `SITE_TYPES` defect one register
    #   along.
    booked = AT.markings_for_project(proj.get("id"))
    loose = AT.unattributed_at_site(aid)
    others = PJ.others_on_site(aid, except_id=proj.get("id"))
    note = _labour_note(proj, others, loose)

    # ── Empty state 2: a site, and nothing marked on it ─────────────────────
    if not booked and not loose:
        return (f'<p class="sl-lead">{note}</p>'
                f'<p class="sl-empty">No attendance has been marked at this '
                f'site. Nobody has been recorded as working here.</p>')

    multiplier = S.ot_multiplier()
    return (f'<p class="sl-lead">{note}</p>'
            f'{_labour_group(booked, multiplier, "booked")}'
            f'{_labour_group(loose, multiplier, "loose")}')


# ⚠ **The two groups render through ONE function, so they cannot drift into two
#   designs.** What differs is the caption and the wording of the shortfall
#   line; the row, the columns and the sum are the same, because they are the
#   same kind of record shown twice.
_GROUP_CAPTION = {
    "booked": (
        "Booked to this project",
        'Markings whose project is <b>this</b> one &mdash; an id somebody chose '
        'from a picker filtered to this site, exactly as a charge carries the '
        'project it was entered against.'),
    "loose": (
        "At this site, unattributed",
        '&#9888; Markings booked at this project&rsquo;s <b>site</b> that are '
        '<b>attributed to no project at all</b>. They are shown here because '
        'they were booked at this site &mdash; not because they belong to this '
        'project, which nothing in the data says. Open one and pick its project '
        'to attribute it.'),
}


def _labour_group(rows, multiplier, kind: str) -> str:
    """
    One labelled group of markings, its own column added up.

    ⚠ **A SUM DOWN THIS GROUP'S OWN COLUMN, which is what the docstring at the
    top of this file permits in its FIRST sentence** — *"Each panel shows the
    documents' OWN values and adds that one column up"* — and what `_sum_cell()`
    already does for the five panels above. **Two sums inside one panel is still
    one panel**, and the prohibition is the second sentence: a figure that only
    exists by **combining** two of them. ⚠ **Nothing anywhere adds these two
    together**, and nothing may: the whole point of separating them is that one
    is attributed and the other is not, so a combined figure would state
    precisely the thing the page says cannot be determined.

    ⚠ **A REFUSED MARKING SITS THE SUM OUT and the reader is told how many.**
    `_sum_cell()` already drops a `None`; what it cannot do is say the total is
    short. Silently excluding an old-model marking would understate the group by
    an unknown amount that looks exactly like a complete figure —
    `/attendance/` states its own shortfall for that reason and so does this.
    """
    title, blurb = _GROUP_CAPTION[kind]
    if not rows:
        # ⚠ An empty group is stated, not hidden. "No unattributed markings" is
        #   a fact worth reading — it is what says the figure above is complete.
        empty = ("No markings are booked to this project."
                 if kind == "booked" else
                 "Every marking at this site is attributed to a project.")
        return (f'<div class="sl-group"><div class="sl-group-head">{title}</div>'
                f'<p class="sl-empty">{empty}</p></div>')

    body = ""
    vals, refused = [], 0
    for r in rows:
        cells = AT.marking_cells(r, multiplier)
        if cells["refused"]:
            refused += 1
        else:
            vals.append(cells["total"])
        body += f"""
        <tr class="{cells['row_class']}">
          <td>{P.esc(r.get('date'))}</td>
          <td>{cells['employee']}</td>
          <td>{cells['status']}</td>
          <td class="num">{cells['ot']}</td>
          {cells['money']}
        </tr>"""

    # ⚠ **The shortfall sits BELOW the table, next to the figure it qualifies.**
    #   It read "not costed above" while rendering above the table, which was
    #   true of nothing; moving it under the Total row makes the sentence true
    #   and puts the caveat where the number is. The wording is unchanged.
    short = ""
    if refused:
        one = refused == 1
        short = (f'<div class="sl-short">&#9888; {refused} marking'
                 f'{"" if one else "s"} {"is" if one else "are"} not costed '
                 f'above &mdash; the day rate on {"it" if one else "them"} '
                 f'predates the day-rate correction and was never re-entered. '
                 f'The total is short by '
                 f'{"that marking" if one else "those markings"}.</div>')

    body += _total_row(6, _sum_cell(vals))

    return f"""
      <div class="sl-group">
        <div class="sl-group-head">{title}
          <span class="sl-group-count">{len(rows)} marking{"" if len(rows) == 1 else "s"}</span>
        </div>
        <p class="sl-group-note">{blurb}</p>
        <table class="data">
          <thead>
            <tr>
              <th>Date</th>
              <th>Employee</th>
              <th>Status</th>
              <th class="num">OT hours</th>
              <th class="num">Day rate</th>
              <th class="num">Overtime</th>
              <th class="num">Total</th>
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
        {short}
      </div>"""

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

        # ── DETACH — the other half of attach, and the only way back ────────
        #
        # ⚠ **THERE IS NO `/boq/edit` ROUTE IN THIS APPLICATION**, so without
        #   this branch a BOQ filed against the wrong project is filed there
        #   permanently: the attach control above offers only BOQs carrying no
        #   project at all, precisely because moving one between projects
        #   splits a P&L and wants deliberation. Detach is that deliberation —
        #   it puts the schedule back in the unattached pool, where attach can
        #   then pick it up for the right project.
        #
        # ⚠ **It walks the revision chain exactly as attach does, and it must.**
        #   Attach sets `project_id` on every revision; a detach that cleared
        #   only the revision named would leave the rest of the chain pointing
        #   here, which is the split-chain state the attach rule exists to
        #   prevent. `revision_chain()` walks back to the root and forward
        #   through every descendant, so both directions are covered.
        #
        # ⚠ **Only members currently on THIS project are cleared.** A chain
        #   member somehow attached elsewhere is left alone rather than being
        #   silently detached from a project this page is not looking at —
        #   DOMAIN.md §6's rule: this page may not quietly rewrite a record
        #   belonging to somebody else's job.
        if action == "detach_boq":
            boq_id = request.form.get("boq_id")
            if not boq_id:
                return redirect(url_for("projectview.view_project", id=id,
                                        msg="No BOQ selected.", type="error"))
            cleared = 0
            for c_id in revision_chain(boq_id):
                b = STORE["boqs"].get(c_id)
                if b and b.get("project_id") == id:
                    b["project_id"] = ""
                    cleared += 1
            if not cleared:
                return redirect(url_for("projectview.view_project", id=id,
                                        msg="That schedule is not attached to "
                                            "this project.", type="error"))
            return redirect(url_for(
                "projectview.view_project", id=id,
                msg=(f"BOQ chain detached from this project "
                     f"({cleared} revision{'s' if cleared != 1 else ''}). "
                     f"It can now be attached to another."),
                type="success"))

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
    #
    # ⚠ **A `project_id` that names a project which no longer exists counts as
    #   UNATTACHED** (9 September 2026). `/boq/create` stores what the form
    #   posted without checking it against `STORE["projects"]`, and
    #   `/projects/delete/<id>` does not walk the BOQs, so deleting a project
    #   leaves every BOQ that was filed under it pointing at nothing. The
    #   membership test below is what stops that being permanent: without it the
    #   `not b.get("project_id")` above is False for an orphan, so the schedule
    #   is offered by **no** project's attach picker and cannot be re-filed
    #   through the screen at all — invisible, and unfixable without MySQL.
    #
    #   This is `purchase.py`'s existing precedent and deliberately nothing
    #   wider: that module guards the same field at render time with
    #   `if po.get("project_id") in (STORE.get("projects") or {})` and draws a
    #   plain chip instead of a link when it fails. **No validation was added at
    #   POST**, because `purchase.py` has none either and inventing one here
    #   would put two different rules on one field.
    _live_projects = STORE.get("projects") or {}
    eligible_boqs = [b for b in STORE.get("boqs", {}).values()
                     if (b.get("project_id") or "") not in _live_projects]
    eligible_boqs.sort(key=lambda b: (str(b.get("date") or ""), str(b.get("ref") or "")), reverse=True)
    
    boq_opts = '<option value="">-- Select an unattached BOQ --</option>'
    for b in eligible_boqs:
        boq_opts += f'<option value="{b.get("id")}">{P.esc(b.get("ref"))} - {P.esc(b.get("account_name"))}</option>'

    # ── Detachable BOQs — what is on this project right now ────────────────
    # The mirror of the list above. Offered as a picker rather than a button
    # per row because the unit of both operations is the whole revision chain,
    # not the revision the row happens to show, and a control that sits beside
    # Attach says that where a button inside a row would not.
    detach_opts = '<option value="">-- Select an attached BOQ --</option>'
    for b in attached_boqs:
        detach_opts += (f'<option value="{P.esc(b.get("id"))}">'
                        f'{P.esc(b.get("ref"))} - '
                        f'{P.esc(b.get("account_name") or "unnamed")}</option>')

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

    labour_html = _site_labour(proj)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{B.page_title(proj.get('name', 'Project'))}</title>
  {B.HEAD_ICON}
  {BASE_STYLES}
  {QUOTATION_STYLES}
  <style>{AT.MARKING_CELL_CSS}
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

    /* ── Site Labour ────────────────────────────────────────────────────
       The status pill, the sub-lines and the refusal cell come from
       `attendance.MARKING_CELL_CSS`, spliced into the block above — one copy,
       shared with `/attendance/`, so a marking cannot look like two different
       things on two pages. What is left here is this panel's own furniture. */
    table.data th.num, table.data td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
    .sl-lead {{ font-size:.85rem; color:var(--muted); line-height:1.6; margin:0 0 1rem; }}
    .sl-lead b {{ color:var(--navy); }}
    .sl-empty {{ font-size:.88rem; color:var(--muted); margin:0; }}
    .sl-empty b {{ color:var(--navy); }}
    .sl-empty a {{ color:#1d4ed8; }}
    /* The ambiguity note. Amber, the same `.pm-drift` shape this page already
       uses for the site divergence band — deliberately the house amber rather
       than a second design, because it says the same KIND of thing: here is a
       fact about the data that nothing may silently resolve. */
    .sl-ambig {{ display:flex; gap:.6rem; align-items:flex-start;
                 border:1px solid #fde68a; background:#fffbeb; border-radius:8px;
                 padding:.75rem 1rem; margin-top:.85rem;
                 font-size:.83rem; line-height:1.6; color:#6B4E00; }}
    .sl-ambig-icon {{ color:#b45309; font-size:1rem; line-height:1.3; }}
    .sl-ambig b {{ color:#8A5A00; }}
    .sl-ambig a {{ color:#1d4ed8; }}
    /* The shortfall line. Same amber, quieter — it is a caveat on a figure
       rather than a warning about what the figure means. */
    .sl-short {{ background:#FFF6E5; border:1px solid #F0D8A8;
                 border-left:3px solid var(--saffron); border-radius:8px;
                 padding:.6rem .9rem; margin:0 0 1rem;
                 font-size:.82rem; line-height:1.5; color:#6B4E00; }}
    /* ── The two groups ─────────────────────────────────────────────────
       ⚠ The separation has to be VISIBLE, not implied by a blank line. One
       group is attributed and the other is not, and a reader who runs the two
       tables together has read one figure where the page states two. Hence a
       ruled heading per group and a gap between them that is wider than the
       gap inside one. */
    .sl-group {{ margin-top:1.5rem; }}
    .sl-group:first-of-type {{ margin-top:0; }}
    .sl-group-head {{ display:flex; justify-content:space-between;
                      align-items:baseline; gap:1rem;
                      font-size:.82rem; font-weight:700; color:var(--navy);
                      text-transform:uppercase; letter-spacing:.05em;
                      padding-bottom:.4rem; margin-bottom:.5rem;
                      border-bottom:2px solid var(--border); }}
    .sl-group-count {{ font-weight:400; text-transform:none; letter-spacing:0;
                       color:var(--muted); }}
    .sl-group-note {{ font-size:.8rem; color:var(--muted); line-height:1.6;
                      margin:0 0 .8rem; }}
    .sl-group-note b {{ color:var(--navy); }}
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
        <div style="border-left:1px solid var(--border); padding-left:1.5rem;">
          <p style="margin:0 0 0.5rem 0; font-weight:600; font-size:0.9rem;">Detach (Detaches entire revision chain)</p>
          <form method="POST" action="{url_for('projectview.view_project', id=id)}" style="display:flex; gap:0.5rem;">
            <input type="hidden" name="action" value="detach_boq">
            <select name="boq_id" class="form-control" style="min-width:250px;" required>
              {detach_opts}
            </select>
            <button type="submit" class="btn btn-ghost">Detach</button>
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

    <!-- Site Labour Panel -->
    <!-- ⚠ The sub-title here is NOT the charges panel's wording and must never
         be made to match it. That one reads "Expenses tagged to this project"
         and is true of every row in it. Here it is true of the FIRST group and
         false of the second, which is exactly why the panel is split and why
         each group carries its own caption. Conflating the two mechanisms is how
         the same day's labour gets counted on four projects. -->
    <div class="panel">
      <div class="panel-head">
        <h2>Site Labour</h2>
        <span style="font-size:0.8rem;color:var(--muted);">Booked to this project, and booked at its site with no project &mdash; summed separately</span>
      </div>
      {labour_html}
    </div>

  </main>
</body>
</html>"""
    return _page(html)
