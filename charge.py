"""
charge.py — Business Expenses Ledger  (travel, food, wages, consumables)
========================================================================

⚠ **This file was titled "Employee & Miscellaneous Charges Ledger" until
29 August 2026, and the title was wrong in a way that mattered.** There was no
employee record anywhere in the application behind it — PROGRESS.md §6-E
recorded exactly that — so "employee" here named a **free-text `person` field
somebody types**, not a person the system knows. A reader could reasonably have
concluded that this module was the employee master, and that C4 was therefore
partly built. It was not.

Now that a real employee master exists (`employee.py`, CLIENT_CHANGES-2.md
**C4**, 29 August 2026), that title is not merely loose but actively
misleading, so it is corrected here.

⚠ **The MODULE IS NOT RENAMED, deliberately.** `charge.py`, `charge_bp`,
`/charge`, `STORE["charges"]` and `charge.*` in `auth.PERMISSIONS` all stay
exactly as they are. A rename would touch the route registry, the access
matrix, the dashboard, `projectview.py` and every test that names an endpoint —
a wide change, for a word. **What was wrong was the description, so the
description is what changed.**

What this ledger is: business expenses that appear on no BOQ — travel, food,
wages paid out, consumables, site expenses. `person` is free text and stays
free text; it is **not** a foreign key to `employee.py` and must not become one
in this pass. Linking the two is part of **C5** (attendance and site-wise
labour cost), which is gated and not authorised.
"""

import uuid
from flask import Blueprint, redirect, request, url_for

import approval
import attachment
import branding as B
import pipeline as P
from store import STORE
from dashboard import BASE_STYLES, _nav, ICONS, rupees
from quotation import QUOTATION_STYLES

charge_bp = Blueprint("charge", __name__, url_prefix="/charge")

DEFAULT_HEADS = ["Travel", "Food & Meals", "Wages / Labour", "Consumables",
                 "Tools & Equipment", "Transport / Freight", "Accommodation",
                 "Site Expenses", "Other"]

def _heads():
    return STORE.get("settings", {}).get("charge_heads", {}).get("heads", DEFAULT_HEADS)

def _page(html: str) -> str:
    return html

def _esc(v) -> str:
    return P.esc(str(v or ""))

def _alert(msg: str, kind: str = "error") -> str:
    return f'<div class="alert {_esc(kind)}">{_esc(msg)}</div>' if msg else ""

def _flash() -> str:
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "success" if request.args.get("type") == "success" else "error"
    return _alert(msg, kind)

def _now() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def _persons() -> list:
    persons = set()
    for charge in STORE.get("charges", {}).values():
        person = charge.get("person")
        if person:
            persons.add(person)
    return sorted(list(persons))

CHARGE_STYLES = """
<style>
.ledger-table {
    width: 100%; border-collapse: collapse; margin-top: 1rem;
}
.ledger-table th {
    text-align: left; padding: 0.5rem; border-bottom: 2px solid var(--border); font-size: 0.85rem;
}
.ledger-table td {
    padding: 0.5rem; border-bottom: 1px solid var(--border); font-size: 0.85rem;
}
.ledger-table tr:nth-child(even) {
    background-color: var(--surface);
}
.summary-row {
    font-weight: bold; background-color: var(--surface);
}
.cl-amt { text-align: right; }
.cl-desc { text-transform: capitalize; }
</style>
"""

def _shell(title: str, body: str) -> str:
    return _page(f'''<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{CHARGE_STYLES}{attachment.ATTACHMENT_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
</main>
</body></html>''')

def _validate(form) -> tuple:
    data = {
        "date": (form.get("date") or "").strip(),
        "person": (form.get("person") or "").strip(),
        "head": (form.get("head") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "project_id": (form.get("project_id") or "").strip(),
        "taxable_amount_raw": (form.get("taxable_amount") or "").strip(),
        "gst_rate_raw": (form.get("gst_rate") or "0").strip(),
        "notes": (form.get("notes") or "").strip(),
    }
    
    if not data["date"]:
        return data, "Date is required."
    if not data["person"]:
        return data, "Person is required."
    if not data["head"]:
        return data, "Head is required."
        
    taxable = float(P.parse_money(data["taxable_amount_raw"]) or 0.0)
    if taxable <= 0:
        return data, "Taxable amount must be greater than zero."
        
    gst_rate = float(P.parse_money(data["gst_rate_raw"]) or 0.0)
    
    data["taxable_amount"] = round(taxable, 2)
    data["gst_rate"] = round(gst_rate, 2)
    data["gst_amount"] = round(taxable * gst_rate / 100, 2)
    
    return data, ""

@charge_bp.route("/")
def list_charges():
    proj_filter = request.args.get("project_id", "")
    person_filter = request.args.get("person", "")
    head_filter = request.args.get("head", "")
    
    charges = STORE.get("charges", {}).values()
    
    if proj_filter:
        charges = [c for c in charges if c.get("project_id") == proj_filter]
    if person_filter:
        charges = [c for c in charges if c.get("person") == person_filter]
    if head_filter:
        charges = [c for c in charges if c.get("head") == head_filter]
        
    rows = sorted(charges, key=lambda c: (c.get("date", ""), c.get("id", "")), reverse=True)
    
    total_taxable = sum(c.get("taxable_amount", 0.0) for c in rows)
    total_gst = sum(c.get("gst_amount", 0.0) for c in rows)
    total_gross = total_taxable + total_gst
    
    body = "".join(
        f'<tr>'
        f'<td>{_esc(r.get("date"))}</td>'
        f'<td class="cl-desc">{_esc(r.get("person"))}</td>'
        f'<td class="cl-desc">{_esc(r.get("head"))}</td>'
        f'<td>{_esc(r.get("description"))}</td>'
        f'<td class="cl-desc">{_esc(r.get("project_name")) or "General"}</td>'
        f'<td class="cl-amt">{rupees(r.get("taxable_amount", 0.0))}</td>'
        f'<td class="cl-amt">{rupees(r.get("gst_amount", 0.0))}</td>'
        f'<td class="cl-amt">{rupees(r.get("taxable_amount", 0.0) + r.get("gst_amount", 0.0))}</td>'
        # B8 — the supporting document, reachable from the register. A charge
        # raised before 2 September 2026 has none and says so rather than
        # rendering an empty cell that reads like a missing file.
        f'<td>{_doc_cell(r.get("id"))}</td>'
        # B6 — the approval state, the ladder actions, and the "creator
        # unknown" chip for a record that predates the approval system. Screen
        # only; no charge is printed anywhere and nothing here reaches paper.
        f'<td>{approval.cell("charge", r)}</td>'
        f'<td><a class="btn btn-ghost" href="{url_for("charge.edit_charge", id=r.get("id"))}">Edit</a> '
        f'<a class="btn btn-ghost" href="{url_for("charge.delete_charge", id=r.get("id"))}">Delete</a></td>'
        f'</tr>'
        for r in rows
    )
    empty = '<tr><td colspan="11" style="color:var(--muted); text-align:center;">No charges found.</td></tr>'
    
    proj_options = '<option value="">All Projects</option>'
    for pid, p in sorted(STORE.get("projects", {}).items(), key=lambda kv: kv[1].get("name", "")):
        sel = " selected" if pid == proj_filter else ""
        proj_options += f'<option value="{_esc(pid)}"{sel}>{_esc(p.get("name"))}</option>'
        
    person_options = '<option value="">All Persons</option>'
    for p in _persons():
        sel = " selected" if p == person_filter else ""
        person_options += f'<option value="{_esc(p)}"{sel}>{_esc(p)}</option>'
        
    head_options = '<option value="">All Heads</option>'
    for h in _heads():
        sel = " selected" if h == head_filter else ""
        head_options += f'<option value="{_esc(h)}"{sel}>{_esc(h)}</option>'
        
    return _shell("Ledger", f"""
  <div class="page-top">
    <h1>Charges <span>Ledger</span></h1>
    <a href="{url_for('charge.new_charge')}" class="btn">&#43; Add Charge</a>
  </div>
  {_flash()}
  
  <div class="form-section" style="padding: 1rem; margin-bottom: 1rem;">
    <form method="GET" action="{url_for('charge.list_charges')}" style="display:flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap;">
      <div class="form-group" style="margin-bottom:0;"><label>Project</label>
        <select name="project_id">{proj_options}</select></div>
      <div class="form-group" style="margin-bottom:0;"><label>Person</label>
        <select name="person">{person_options}</select></div>
      <div class="form-group" style="margin-bottom:0;"><label>Head</label>
        <select name="head">{head_options}</select></div>
      <button type="submit" class="btn btn-ghost">Filter</button>
      <a href="{url_for('charge.list_charges')}" class="btn btn-ghost">Clear</a>
    </form>
  </div>
  
  <div class="form-section">
    <table class="ledger-table">
      <thead><tr>
        <th>Date</th>
        <th>Person</th>
        <th>Head</th>
        <th>Description</th>
        <th>Project</th>
        <th class="cl-amt">Taxable</th>
        <th class="cl-amt">GST</th>
        <th class="cl-amt">Gross</th>
        <th>Document</th>
        <th>Approval</th>
        <th></th>
      </tr></thead>
      <tbody>{body or empty}</tbody>
      <tfoot>
        <tr class="summary-row">
            <td colspan="5" style="text-align:right;">Total:</td>
            <td class="cl-amt">{rupees(total_taxable)}</td>
            <td class="cl-amt">{rupees(total_gst)}</td>
            <td class="cl-amt">{rupees(total_gross)}</td>
            <td></td>
            <td></td>
            <td></td>
        </tr>
      </tfoot>
    </table>
  </div>
    """)

# A dash rather than an empty cell: a charge raised before 2 September 2026 has
# no attachment, and a blank cell reads like a file that failed to render.
_NO_DOC = '<span class="att-none">&mdash;</span>'


def _doc_cell(charge_id: str) -> str:
    return attachment.panel("charge", charge_id) or _NO_DOC


def _attachment_warning(charge_id: str) -> str:
    """
    Name the files the cascade is about to destroy, before it destroys them.

    The operator should know a supplier bill is going with the charge at the
    moment they confirm, not discover it afterwards — the same reasoning
    `receipt.delete_receipt()` already applies to the bills that froze a balance.
    """
    files = attachment.for_parent("charge", charge_id)
    if not files:
        return ""
    names = ", ".join(_esc(a.get("filename")) for a in files)
    word = "file" if len(files) == 1 else "files"
    return (f'<div class="del-line">The attached {word} <b>{names}</b> '
            f'will be deleted with it.</div>')


def _form(data: dict, error: str, action: str, submit_label: str) -> str:
    proj_options = '<option value="">General (No Project)</option>'
    for pid, p in sorted(STORE.get("projects", {}).items(), key=lambda kv: kv[1].get("name", "")):
        sel = " selected" if pid == data.get("project_id") else ""
        proj_options += f'<option value="{_esc(pid)}"{sel}>{_esc(p.get("name"))}</option>'
        
    head_options = ''
    for h in _heads():
        sel = " selected" if h == data.get("head") else ""
        head_options += f'<option value="{_esc(h)}"{sel}>{_esc(h)}</option>'
        
    person_list = "".join(f'<option value="{_esc(p)}"></option>' for p in _persons())
    
    return _shell("Charge Entry", f"""
  <div class="page-top">
    <h1>Charge <span>Entry</span></h1>
    <a href="{url_for('charge.list_charges')}" class="btn btn-ghost">&#8592; Back</a>
  </div>
  {_alert(error)}
  <!-- ⚠ enctype is load-bearing. Without it the browser posts the FILENAME as
       an ordinary string, `request.files` is empty, and a compulsory
       attachment looks exactly like an operator who attached nothing.
       tests/test_attachments.py asserts it on this form. -->
  <form method="POST" action="{action}" enctype="multipart/form-data">
    <div class="form-section">
      <div class="section-title">Expense Details</div>
      
      <div class="fg2">
        <div class="form-group"><label>Date</label>
          <input type="date" name="date" value="{_esc(data.get('date'))}" /></div>
        <div class="form-group"><label>Project</label>
          <select name="project_id">{proj_options}</select></div>
      </div>
      
      <div class="fg2">
        <div class="form-group"><label>Person</label>
          <input type="text" name="person" list="person_list" value="{_esc(data.get('person'))}" />
          <datalist id="person_list">{person_list}</datalist></div>
        <div class="form-group"><label>Head</label>
          <select name="head"><option value="">-- Select --</option>{head_options}</select></div>
      </div>
      
      <div class="form-group"><label>Description</label>
        <textarea name="description" rows="2">{_esc(data.get('description'))}</textarea></div>
        
      <div class="fg2">
        <div class="form-group"><label>Taxable Amount</label>
          <input type="text" name="taxable_amount" value="{_esc(data.get('taxable_amount_raw', data.get('taxable_amount', '')))}" /></div>
        <div class="form-group"><label>GST Rate (%)</label>
          <input type="text" name="gst_rate" value="{_esc(data.get('gst_rate_raw', data.get('gst_rate', '0')))}" /></div>
      </div>
      
      <div class="form-group"><label>Notes</label>
        <input type="text" name="notes" value="{_esc(data.get('notes'))}" /></div>

      <!-- B8. Compulsory here and optional on a receipt — CC-2's asymmetry,
           carried as data in attachment.PARENTS rather than as a branch. -->
      {attachment.upload_field("charge", data.get("id") or "")}

    </div>
    <div style="display:flex;gap:.7rem;">
      <button type="submit" class="btn">{_esc(submit_label)}</button>
      <a href="{url_for('charge.list_charges')}" class="btn btn-ghost">Cancel</a>
    </div>
  </form>
    """)

@charge_bp.route("/new", methods=["GET", "POST"])
def new_charge():
    import datetime
    today = datetime.date.today().isoformat()
    data = {"date": today}
    error = ""
    
    if request.method == "POST":
        data, error = _validate(request.form)

        # ── B8. THE ATTACHMENT IS COMPULSORY ON A CHARGE ────────────────────
        #
        # CC-2's B8: *"Charges: attachment is compulsory (client requirement)"*,
        # and the 19 August list: *"Compulsory document ATTACHMENT in the charge
        # section"*. Read literally.
        #
        # ⚠ **Validated BEFORE the charge record is written, and the charge is
        #   not written at all if the file is bad.** The alternative — save the
        #   charge, then fail on the file — leaves exactly the record CC-2 says
        #   may not exist: a charge with no supporting document. `save()` needs
        #   the charge's id, so the *write* has to come after; the *validation*
        #   does not, and that is the split.
        #
        # ⚠ **A rejected form loses the chosen file and there is no fixing
        #   that.** A browser will not re-populate a file input from a server
        #   response — it is the same rule that stops a page reading the disk.
        #   So the operator re-picks the file when any other field is wrong,
        #   which is why the file is validated in the same pass as everything
        #   else rather than in a second round trip.
        upload = request.files.get("attachment")
        if not error:
            ok, why, _mime, _size = attachment.validate(upload)
            if not ok:
                error = why
        if not error:
            cid = str(uuid.uuid4())
            proj_name = ""
            if data["project_id"] and data["project_id"] in STORE.get("projects", {}):
                proj_name = STORE["projects"][data["project_id"]].get("name", "")
                
            STORE.setdefault("charges", {})[cid] = {
                "id": cid,
                "date": data["date"],
                "person": data["person"],
                "head": data["head"],
                "description": data["description"],
                "project_id": data["project_id"],
                "project_name": proj_name,
                "taxable_amount": data["taxable_amount"],
                "gst_rate": data["gst_rate"],
                "gst_amount": data["gst_amount"],
                "notes": data["notes"],
                "created_at": _now(),
                "updated_at": _now()
            }
            # B6 — the creator is captured HERE, at the write site, because the
            # rule that a person may not approve their own record needs the
            # creator recorded at the one moment there is one.
            approval.stamp_creator(STORE["charges"][cid])

            # The file, now that there is an id to hang it on. Validated above,
            # so this cannot fail on anything the operator could have fixed.
            _rec, att_err = attachment.save(upload, "charge", cid)
            if att_err:
                # Belt and braces: the charge is rolled back rather than left
                # standing without the document CC-2 requires.
                STORE["charges"].pop(cid, None)
                return _form(data, att_err, action=url_for("charge.new_charge"),
                             submit_label="Save Charge")

            return redirect(url_for("charge.list_charges", msg="Charge saved.", type="success"))
            
    return _form(data, error, action=url_for("charge.new_charge"), submit_label="Save Charge")

@charge_bp.route("/edit/<id>", methods=["GET", "POST"])
def edit_charge(id: str):
    charge = STORE.get("charges", {}).get(id)
    if not charge:
        return redirect(url_for("charge.list_charges", msg="Charge not found.", type="error"))

    # B7 (ours, see approval.can_modify): an approved charge is locked, a
    # part-climbed one is locked, and an unapproved one belongs to whoever
    # raised it. Refused BY URL — hiding the Edit link is not a gate.
    may, why_not = approval.can_modify("charge", charge)
    if not may:
        return redirect(url_for("charge.list_charges", msg=why_not, type="error"))

    data = dict(charge)
    data["taxable_amount_raw"] = str(data.get("taxable_amount", ""))
    data["gst_rate_raw"] = str(data.get("gst_rate", ""))
    error = ""

    if request.method == "POST":
        data, error = _validate(request.form)
        data["id"] = id

        # ── B8 on an EDIT: adding a file is optional, and that is the
        #    GRANDFATHER rule rather than a softening of the requirement.
        #
        # Every charge raised before 2 September 2026 has no attachment, and
        # requiring one here would mean an operator could not fix a typo on a
        # historical charge without first finding a two-month-old paper bill to
        # photograph. That is the same reasoning `approval.is_grandfathered()`
        # rests on everywhere else in this application: a gate is applied to
        # what happens next, not retrospectively to what already exists.
        #
        # ⚠ **The requirement is NOT weakened for new charges.**
        #   `new_charge()` refuses without a file, and
        #   `attachment._do_delete()` refuses to remove the last one from a
        #   charge that has any. Those two are the whole rule; this is the one
        #   door that was already open before the rule existed.
        upload = request.files.get("attachment")
        has_file = bool(upload and (upload.filename or "").strip())
        if not error and has_file:
            ok, why, _m, _s = attachment.validate(upload)
            if not ok:
                error = why
        if not error:
            proj_name = ""
            if data["project_id"] and data["project_id"] in STORE.get("projects", {}):
                proj_name = STORE["projects"][data["project_id"]].get("name", "")
                
            charge.update({
                "date": data["date"],
                "person": data["person"],
                "head": data["head"],
                "description": data["description"],
                "project_id": data["project_id"],
                "project_name": proj_name,
                "taxable_amount": data["taxable_amount"],
                "gst_rate": data["gst_rate"],
                "gst_amount": data["gst_amount"],
                "notes": data["notes"],
                "updated_at": _now()
            })
            # An approval describes the document somebody read, so a changed
            # document has not been approved. Only reachable for a REJECTED
            # charge going back through the ladder — can_modify() refuses every
            # other state that carries a rung.
            approval.clear_approvals(charge)

            if has_file:
                attachment.save(upload, "charge", id)

            return redirect(url_for("charge.list_charges", msg="Charge updated.", type="success"))
            
    return _form(data, error, action=url_for("charge.edit_charge", id=id), submit_label="Update Charge")

@charge_bp.route("/delete/<id>", methods=["GET", "POST"])
def delete_charge(id: str):
    charge = STORE.get("charges", {}).get(id)
    if not charge:
        return redirect(url_for("charge.list_charges", msg="Charge not found.", type="error"))

    # Same guard as edit: deleting an approved charge is a stronger act than
    # editing one, so it cannot be the looser of the two.
    may, why_not = approval.can_modify("charge", charge)
    if not may:
        return redirect(url_for("charge.list_charges", msg=why_not, type="error"))

    if request.method == "POST":
        # ── B8's cascade. CC-2: *"Deleting the parent record deletes its file.
        #    No orphans."* Both halves — the bytes on disk AND the metadata row.
        #
        # ⚠ **Before the charge is popped, not after.** `delete_for_parent()`
        #   finds its rows by `parent_id`, which does not need the parent to
        #   still exist — but the ordering matters if this ever raises: a
        #   charge that survived a failed cascade can be deleted again, while
        #   files whose charge is already gone are reachable from no page.
        attachment.delete_for_parent("charge", id)
        STORE["charges"].pop(id, None)
        return redirect(url_for("charge.list_charges", msg="Charge deleted.", type="success"))
        
    return _shell("Delete Charge", f"""
  <div class="page-top"><h1>Delete <span>Charge</span></h1></div>
  <div class="del-box">
    <h2>&#9888; This cannot be undone</h2>
    <div class="del-line">
      You are about to delete the charge of <b>{rupees(charge.get('taxable_amount', 0) + charge.get('gst_amount', 0))}</b> 
      for <b>{_esc(charge.get('person'))}</b> on {_esc(charge.get('date'))}.
    </div>
    {_attachment_warning(id)}
  </div>
  <form method="POST" action="{url_for('charge.delete_charge', id=id)}"
        style="display:flex;gap:.7rem;">
    <button type="submit" class="btn">Delete charge</button>
    <a href="{url_for('charge.list_charges')}" class="btn btn-ghost">Keep it</a>
  </form>
    """)
