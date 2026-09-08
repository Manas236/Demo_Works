"""
auth.py — Identity, roles and access control
============================================
Phase 3B (CLIENT_CHANGES-2.md §B). Users, sessions, named permissions, roles as
editable data, and the default-deny hook that gates every route in the app.

Read CLIENT_CHANGES-2.md §B before changing anything here. Three of its rules
are load-bearing and are held by code in this file rather than by convention:

* **B2 — permissions are named strings, minted in code.** The client may bundle
  existing permissions into roles; the client may not invent a permission
  string. A typo'd permission either silently grants nothing or makes a route
  unreachable, so `/roles/edit` renders checkboxes over `PERMISSIONS` and
  discards anything posted that is not a key of it.

* **B3 — the Owner / Admin split.** An **Owner** defines what a role *means*;
  an **Admin** creates users, deactivates them, and assigns roles that already
  exist. There is no `tier` field: Owner is exactly "holds `admin.roles`",
  which keeps one mechanism instead of two that can disagree. `_may_grant()`
  is what stops an Admin promoting themselves by assigning the Owner role, and
  `_would_strand_install()` is what stops the last Owner being locked out.

* **B5 — default deny.** `_gate()` refuses any endpoint **absent** from
  `ROUTE_PERMISSIONS`. A route added later without a registry entry fails
  closed. That is the whole reason this is a central registry rather than a
  decorator: a decorator scheme fails *open* on the one mistake that matters.

Import direction
----------------
**This module imports nothing that prints.** Every other module may import it.
`dashboard.py` does, to decide whether to draw the Access card — which is why
the chrome import here is inside the function body, the precedent
`dashboard.index()` already sets for `product` and `address` (ABOUT.md §2).
"""

import datetime
import os
import pathlib
import secrets
import sys
import uuid
from collections import deque

from flask import Blueprint, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import branding as B
import pipeline as P
from store import STORE

auth_bp = Blueprint("auth", __name__)

# How long a session survives. CLIENT_CHANGES-2.md names no figure; 12 hours
# covers a working day without leaving a browser logged in overnight.
SESSION_HOURS = 12

# The session holds the user id and nothing else. Permissions are resolved from
# the store on every request, so an Owner editing a role takes effect on that
# user's next click rather than on their next login — which is the entire point
# of roles being data (B2).
SESSION_KEY = "uid"


# =============================================================================
# SECRET_KEY  (B1 — "not a separate task")
# =============================================================================

SECRET_FILE = pathlib.Path(__file__).resolve().parent / "secret_key.txt"


def resolve_secret_key() -> str:
    """
    A real signing key, in three steps, with **no demo fallback**.

    `app.secret_key` used to default to the literal `"qms-demo-secret-2024"`
    (ABOUT.md §7 gap 8). With no sessions that was untidy; with sessions live it
    is session forgery — a value published in a git history signs any cookie an
    attacker cares to mint, so every role check below becomes theatre. The
    hardcoded value is deleted rather than demoted, because a fallback that only
    fires "in development" is a fallback that ships.

    1. `SAMRUDDHI_SECRET_KEY` — the deployment-supplied value.
    2. `SECRET_KEY` — honoured because `tests/conftest.py` has set it since long
       before this module existed, and a live install may already carry it. It
       is read, never written.
    3. `secret_key.txt` beside this file — read if present, minted if not. It is
       gitignored alongside `backups/`.
    """
    return resolve_secret_key_with_source()[0]


def resolve_secret_key_with_source() -> tuple:
    """
    `(key, source)` — the same three steps, saying which one answered.

    Split out so `install()` can say **where the key came from** without
    re-deriving it. `source` is one of the two environment variable names,
    `"file"` for an existing `secret_key.txt`, or `"minted"` for one written on
    this boot. `resolve_secret_key()` is the unchanged one-value form and every
    existing caller and test still uses it.
    """
    for var in ("SAMRUDDHI_SECRET_KEY", "SECRET_KEY"):
        env = (os.getenv(var) or "").strip()
        if env:
            return env, var

    try:
        existing = SECRET_FILE.read_text(encoding="utf8").strip()
        if existing:
            return existing, "file"
    except OSError:
        pass

    minted = secrets.token_hex(32)
    try:
        SECRET_FILE.write_text(minted, encoding="utf8")
    except OSError:
        # A read-only checkout still gets a working key; it just will not
        # survive a restart, which logs everybody out rather than failing open.
        pass
    return minted, "minted"


# The two sources that mean "nobody configured a key for this deployment".
FALLBACK_SOURCES = ("file", "minted")


def secret_key_warning(source: str) -> str:
    """
    The startup banner for a key nobody supplied, or `""` when one was.

    ⚠ **IT WARNS, IT DOES NOT REFUSE TO START** (CC-2, "Security items promoted
      by this phase"). Failing hard on a missing variable would break the dev
      flow and take the test suite with it, and a developer who cannot start
      the app does not read the reason — they set the variable to anything at
      all, which is worse than the fallback. The fallback key is a real random
      256-bit value either way; what is missing is a *deployment* deciding it,
      and the thing worth saying is that sessions will not survive losing that
      file and are not shared with any other instance.

    Returned rather than printed so it can be asserted without capturing
    stdout — `tests/test_auth.py` checks the text, and `install()` prints it.
    """
    if source not in FALLBACK_SOURCES:
        return ""
    minted = source == "minted"
    return "\n".join((
        "",
        "  " + "=" * 72,
        "  ⚠  SECRET_KEY IS NOT SET — this app is signing sessions with a",
        "     LOCAL key it " + ("just generated." if minted else "keeps in secret_key.txt."),
        "",
        "     Set SAMRUDDHI_SECRET_KEY (or SECRET_KEY) for anything that is not",
        "     one developer's own machine. Until then:",
        "",
        "       * every session cookie is invalidated if secret_key.txt is lost,",
        "         which signs every user out;",
        "       * a second instance of this app cannot read the first's sessions;",
        "       * the key is on disk beside the code rather than in the",
        "         deployment's own configuration.",
        "",
        f"     key source: {'newly minted ' if minted else ''}{SECRET_FILE}",
        "  " + "=" * 72,
        "",
    ))


# =============================================================================
# THE PERMISSION CATALOGUE  (B2)
# =============================================================================
# Derived from `app.url_map`, not invented: every id below gates at least one
# real endpoint in `ROUTE_PERMISSIONS`, and `tests/test_access_control.py`
# asserts in both directions that the two stay in step.
#
# Naming is `<module>.<action>`. `group` is display only — it is what the role
# editor renders its checkbox blocks from.

PERMISSIONS = {
    # id                     (human label,                                group)
    "dashboard.view":        ("View the dashboard",                       "General"),
    "extractor.view":        ("View market news",                         "General"),

    "boq.view":              ("View bills of quantities",                 "BOQ chain"),
    "boq.create":            ("Create and revise a BOQ",                  "BOQ chain"),
    "boq.print":             ("Print a BOQ",                              "BOQ chain"),

    "ra.view":               ("View RA bills",                            "RA billing"),
    "ra.create":             ("Raise an RA bill",                         "RA billing"),
    "ra.edit":               ("Edit a draft RA bill",                     "RA billing"),
    "ra.delete":             ("Delete a draft RA bill",                   "RA billing"),
    "ra.issue":              ("Issue an RA bill",                         "RA billing"),
    "ra.cancel":             ("Cancel an issued RA bill",                 "RA billing"),
    "ra.print":              ("Print an RA bill",                         "RA billing"),
    "ra.approve":            ("Approve or reject an RA bill",             "RA billing"),

    "receipt.view":          ("View receipts",                            "Money in"),
    "receipt.create":        ("Record a receipt",                         "Money in"),
    "receipt.edit":          ("Edit a receipt",                           "Money in"),
    "receipt.delete":        ("Delete a receipt",                         "Money in"),
    "client.view":           ("View the client register",                 "Money in"),
    "client.edit":           ("Edit a client's party details",            "Money in"),

    "quotation.view":        ("View quotations",                          "Quotation chain"),
    "quotation.create":      ("Create a quotation",                       "Quotation chain"),
    "quotation.edit":        ("Update a quotation's deal fields",         "Quotation chain"),
    "proforma.view":         ("View proforma invoices",                   "Quotation chain"),
    "proforma.create":       ("Raise a proforma invoice",                 "Quotation chain"),
    "invoice.view":          ("View tax invoices",                        "Quotation chain"),
    "invoice.create":        ("Raise a tax invoice",                      "Quotation chain"),
    "invoice.approve":       ("Approve or reject a tax invoice",          "Quotation chain"),

    "purchase.view":         ("View purchase orders",                     "Buy side"),
    "purchase.create":       ("Raise a purchase order",                   "Buy side"),
    "purchase.edit":         ("Update a purchase order's status",         "Buy side"),
    "purchase.approve":      ("Approve or reject a purchase order",       "Buy side"),
    "po.view":               ("View draft purchase orders",               "Buy side"),
    "po.create":             ("Raise a draft purchase order",             "Buy side"),
    "po.edit":               ("Edit a draft purchase order",              "Buy side"),
    "po.delete":             ("Delete a draft purchase order",            "Buy side"),
    "po.print":              ("Print a draft purchase order",             "Buy side"),

    # C2 — the measurement sheet (29 August 2026, fifth override block). It
    # sits in the BOQ chain group beside the schedule it is raised from and the
    # claim it feeds, not in Dispatch: a challan proves goods moved, a
    # measurement proves work was done, and CC-2's C1 keeps the two legs apart.
    #
    # ⚠ **Purchase Manager is REFUSED all six, and that is OUR derivation, not
    #   CC-2's.** They carry `dc.*` because dispatch is theirs; a measurement
    #   feeds an installation claim and belongs to operations and billing. B4
    #   says nothing either way, so this is a **reversible default** — an Owner
    #   grants any of the six at /roles/edit/<id> with a checkbox, no code
    #   change and no re-login.
    #
    #   It is deliberately NOT marked `–` in docs/ACCESS_MATRIX.md, and the
    #   reason is consistency rather than modesty: Purchase Manager already
    #   holds no `ra.*` at all and that absence carries no mark either. Marking
    #   one and not the other would say the two withholdings were reached
    #   differently when they were reached the same way.
    "measurement.view":      ("View measurement sheets",                  "BOQ chain"),
    "measurement.create":    ("Raise a measurement sheet",                "BOQ chain"),
    "measurement.edit":      ("Edit a measurement sheet",                 "BOQ chain"),
    "measurement.delete":    ("Delete a measurement sheet",               "BOQ chain"),
    "measurement.print":     ("Print a measurement sheet",                "BOQ chain"),
    # B6's ladder, on a document B6 does not name. Read approval.py's DOCUMENTS
    # entry for why the RA ladder was chosen and that the choice is ours.
    "measurement.approve":   ("Approve or reject a measurement sheet",    "BOQ chain"),

    "dc.view":               ("View delivery challans",                   "Dispatch"),
    "dc.create":             ("Raise a delivery challan",                 "Dispatch"),
    "dc.edit":               ("Edit a delivery challan",                  "Dispatch"),
    "dc.delete":             ("Delete a delivery challan",                "Dispatch"),
    "dc.print":              ("Print a delivery challan",                 "Dispatch"),

    # CLIENT_CHANGES-2.md B4: "HR information is restricted from Sales,
    # Purchase and Accounts." Until 29 August 2026 `charge.py` — the wages and
    # site-expense ledger — was the only surface that restriction could attach
    # to. The employee master below is now the other, and is the plainer of the
    # two: it carries **salary**.
    "charge.view":           ("View employee and misc charges",           "Employee costs"),
    "charge.create":         ("Record a charge",                          "Employee costs"),
    "charge.edit":           ("Edit a charge",                            "Employee costs"),
    "charge.delete":         ("Delete a charge",                          "Employee costs"),
    # B6 — the approval ladder (29 August 2026). This permission answers
    # "may you reach the approve route at all"; WHICH RUNG your approval
    # satisfies is a question about your ROLE and is answered in
    # approval.py, because B6 states the ladder in role names. Keeping
    # the two apart is what lets an Owner suspend somebody's approval
    # rights with a checkbox without dismantling the ladder.
    "charge.approve":        ("Approve or reject a charge",               "Employee costs"),

    # C4 — the employee master (29 August 2026). ⚠ **Owner, Director and HR
    # only.** That is not a derivation: B4 states exactly one per-role
    # restriction — HR information is kept from Sales, Purchase and Accounts —
    # and a register carrying every employee's salary IS that information.
    # Marked `§` (spec-traced) in docs/ACCESS_MATRIX.md, not `·`.
    "employee.view":         ("View the employee master",                 "Employee costs"),
    "employee.create":       ("Add an employee",                          "Employee costs"),
    "employee.edit":         ("Edit an employee's details and salary",    "Employee costs"),
    "employee.delete":       ("Remove an employee from the register",     "Employee costs"),

    # C5 — attendance and site-wise labour cost. Granted to exactly the roles
    # that hold `employee.*`, for consistency: a muster names the same people
    # and a labour-cost figure is derived from the same salaries, so a role
    # that may not see the master has no business seeing what it costs.
    #
    # ⚠ **Operation Head is REFUSED, and that is OUR derivation, not CC-2's.**
    #   It carries the `–` mark in docs/ACCESS_MATRIX.md — "withheld by our
    #   derivation" — and NOT `§`. B4's one sentence about employee data
    #   ("HR information is restricted from Sales, Purchase and Accounts") does
    #   not name Operations Head in either direction, so a `§` would claim a
    #   backing that does not exist. It is a **reversible default**: an Owner
    #   grants any of these four at /roles/edit/<id> with a checkbox, no code
    #   change and no re-login. PROGRESS.md §4b carries the same ruling for
    #   `employee.*` and this follows it rather than deciding again.
    "attendance.view":       ("View attendance and site-wise labour cost", "Employee costs"),
    "attendance.create":     ("Mark attendance for a day",                "Employee costs"),
    "attendance.edit":       ("Correct an attendance record",             "Employee costs"),
    "attendance.delete":     ("Remove an attendance record",              "Employee costs"),

    "project.view":          ("View projects",                            "Projects"),
    "project.create":        ("Create a project",                         "Projects"),
    "project.edit":          ("Edit a project",                           "Projects"),
    "project.delete":        ("Delete a project",                         "Projects"),

    "spec.view":             ("View the specification library",           "Library"),
    "spec.create":           ("Add a specification",                      "Library"),
    "spec.edit":             ("Edit a specification",                     "Library"),
    "spec.delete":           ("Delete a specification",                   "Library"),
    "product.view":          ("View the product catalogue",               "Library"),
    "product.create":        ("Add a product",                            "Library"),
    "product.delete":        ("Delete a product",                         "Library"),
    "address.view":          ("View the address book",                    "Library"),
    "address.create":        ("Add an address",                           "Library"),
    "address.edit":          ("Edit an address",                          "Library"),
    "address.delete":        ("Delete an address",                        "Library"),

    "settings.edit":         ("Edit company identity and bank details",   "Administration"),
    "admin.users":           ("Create, edit and deactivate users",        "Administration"),
    "admin.roles":           ("Define what a role means",                 "Administration"),
    "admin.access_log":      ("Read the refused-access log",              "Administration"),
}

# Display order for the checkbox blocks in the role editor. A group added to
# PERMISSIONS and forgotten here still renders — `_permission_groups()` appends
# the stragglers rather than dropping them.
GROUP_ORDER = ["General", "BOQ chain", "RA billing", "Money in", "Quotation chain",
               "Buy side", "Dispatch", "Employee costs", "Projects", "Library",
               "Administration"]

# The Owner tier (B3) is exactly "holds `admin.roles`" — the right to change
# what a role *means*, which is the right to grant oneself anything.
OWNER_PERM = "admin.roles"
ADMIN_PERM = "admin.users"


def _permission_groups() -> list:
    """[(group, [(id, label), ...]), ...] in GROUP_ORDER, stragglers last."""
    buckets = {}
    for pid, (label, group) in PERMISSIONS.items():
        buckets.setdefault(group, []).append((pid, label))
    ordered = [g for g in GROUP_ORDER if g in buckets]
    ordered += [g for g in sorted(buckets) if g not in GROUP_ORDER]
    return [(g, buckets[g]) for g in ordered]


# =============================================================================
# THE ROUTE REGISTRY  (B5 — default deny)
# =============================================================================
# Endpoint name -> permission id, or one of the two sentinels.
#
# **An endpoint absent from this map is REFUSED.** That is the design: absence
# is the safe answer, so a route added in a later pass is unreachable until
# somebody classifies it, rather than being world-readable until somebody
# notices. `test_access_control.py::test_every_endpoint_is_classified` fails on
# any unclassified endpoint and is what keeps this map honest — it is
# load-bearing, and weakening it silently re-opens the application.

PUBLIC = "__public__"                # reachable with no session at all
AUTHENTICATED = "__authenticated__"  # any logged-in user, no permission needed

ROUTE_PERMISSIONS = {
    # ── Public ───────────────────────────────────────────────────────────────
    # `/setup` is public *conditionally*: it renders only while `users` is
    # empty and redirects the moment one exists, so the public window closes by
    # itself rather than needing to be closed. See `setup()`.
    "auth.login":                 PUBLIC,
    "auth.setup":                 PUBLIC,
    # Flask registers this whether or not a /static folder exists. This app has
    # none — every asset is a base64 data URI (ABOUT.md §1) — so the rule
    # resolves to a 404, and gating it would only turn that 404 into a redirect.
    "static":                     PUBLIC,

    # ── Any logged-in user ───────────────────────────────────────────────────
    "auth.logout":                AUTHENTICATED,
    "auth.account":               AUTHENTICATED,

    # ── Administration ───────────────────────────────────────────────────────
    "auth.list_users":            "admin.users",
    "auth.create_user":           "admin.users",
    "auth.edit_user":             "admin.users",
    "auth.deactivate_user":       "admin.users",
    "auth.activate_user":         "admin.users",
    "auth.list_roles":            "admin.roles",
    "auth.create_role":           "admin.roles",
    "auth.edit_role":             "admin.roles",
    "auth.access_log":            "admin.access_log",
    "settings.edit_settings":     "settings.edit",

    # ── General ──────────────────────────────────────────────────────────────
    "dashboard.index":            "dashboard.view",
    "extractor.index":            "extractor.view",

    # ── BOQ chain ────────────────────────────────────────────────────────────
    "boq.list_boqs":              "boq.view",
    "boq.view_boq":               "boq.view",
    "boq.create_boq":             "boq.create",
    "boq.print_boq":              "boq.print",

    # ── RA billing ───────────────────────────────────────────────────────────
    "ra.list_ras":                "ra.view",
    "ra.view_ra":                 "ra.view",
    "ra.create_ra":               "ra.create",
    "ra.edit_ra":                 "ra.edit",
    "ra.delete_ra":               "ra.delete",
    "ra.issue_ra":                "ra.issue",
    "ra.cancel_ra":               "ra.cancel",
    "ra.print_ra":                "ra.print",

    # ── C3, the merged RA document (2 September 2026) ───────────────────
    #
    # ⚠ **NO NEW PERMISSION IS MINTED, deliberately.** A merged document is an
    #   RA document — it is built from two RA bills, it lives beside them in the
    #   register, and whoever may see the legs may see their sum. A
    #   `merged_ra.*` family would be four more ids for the same roles to be
    #   granted, and one that reaches no role is the failure §2g records
    #   shipping three times.
    #
    # ⚠ **`create` carries `ra.create` and `cancel` carries `ra.cancel`**, not
    #   `ra.view`. Both write; a read verb on a writing route is §7 gap 24b.
    #   `/merged/create` answers GET and POST under one permission, which is the
    #   ordinary case this registry's caveat covers: the GET renders the picker
    #   and writes nothing, so the stricter of the two is right for both.
    "merged_ra.list_merged":         "ra.view",
    "merged_ra.view_merged":         "ra.view",
    "merged_ra.create_merged":       "ra.create",
    "merged_ra.print_merged":        "ra.print",
    "merged_ra.cancel_merged":       "ra.cancel",

    # ── Money in ─────────────────────────────────────────────────────────────
    "receipt.list_receipts":      "receipt.view",
    "receipt.new_receipt":        "receipt.create",
    "receipt.edit_receipt":       "receipt.edit",
    "receipt.delete_receipt":     "receipt.delete",
    "client.list_clients":        "client.view",
    "client.edit_party":          "client.edit",

    # ── Quotation chain ──────────────────────────────────────────────────────
    "quotation.list_quotations":  "quotation.view",
    "quotation.view_quotation":   "quotation.view",
    "quotation.create_quotation": "quotation.create",
    "quotation.update_quotation": "quotation.edit",
    "proforma.list_proformas":    "proforma.view",
    "proforma.view_proforma":     "proforma.view",
    "proforma.create_proforma":   "proforma.create",
    "invoice.list_invoices":      "invoice.view",
    "invoice.view_invoice":       "invoice.view",
    "invoice.create_invoice":     "invoice.create",

    # ── Buy side ─────────────────────────────────────────────────────────────
    "purchase.list_purchases":    "purchase.view",
    "purchase.view_purchase":     "purchase.view",
    "purchase.create_purchase":   "purchase.create",
    "purchase.from_boq":          "purchase.create",
    "purchase.from_draft":        "purchase.create",
    "purchase.update_purchase":   "purchase.edit",
    # ⚠ **`purchase.create`, deliberately, and not `purchase.edit`.**
    # `purchase.edit` is labelled "Update a purchase order's status" and
    # that is what it means — moving an order along its lifecycle.
    # `/purchase/edit/<id>` changes what this company has agreed to PAY a
    # vendor, which is the same authority `/purchase/create` confers and a
    # strictly larger one than marking a delivery received. Every role that
    # holds `purchase.edit` today also holds `purchase.create`, so this
    # classification moves no cell of the access matrix; it is chosen for
    # the day a storekeeper is given status rights and must not be able to
    # reprice an order. No new permission was minted: inventing one would
    # force a per-role decision that CLIENT_CHANGES-2.md B4 does not
    # authorise us to take on the client's behalf.
    "purchase.edit_purchase_rates": "purchase.create",
    "po_draft.list_pos":          "po.view",
    "po_draft.view_po":           "po.view",
    "po_draft.create_po":         "po.create",
    "po_draft.edit_po":           "po.edit",
    "po_draft.delete_po":         "po.delete",
    "po_draft.print_po":          "po.print",

    # ── Dispatch ─────────────────────────────────────────────────────────────
    "challan.list_dcs":           "dc.view",
    "challan.view_dc":            "dc.view",
    "challan.create_dc":          "dc.create",
    "challan.edit_dc":            "dc.edit",
    "challan.delete_dc":          "dc.delete",
    "challan.print_dc":           "dc.print",

    # ── The measurement sheet (CC-2 C2) ──────────────────────────────────────
    # `/measurement/edit/<id>` and `/measurement/delete/<id>` each answer both
    # GET and POST at one endpoint — the confirm page and the write — exactly as
    # `/dc/delete/<id>` does, so each carries one row.
    "measurement.list_ms":        "measurement.view",
    "measurement.view_ms":        "measurement.view",
    "measurement.create_ms":      "measurement.create",
    "measurement.edit_ms":        "measurement.edit",
    "measurement.delete_ms":      "measurement.delete",
    "measurement.print_ms":       "measurement.print",

    # ── Employee costs ───────────────────────────────────────────────────────
    "charge.list_charges":        "charge.view",
    "charge.new_charge":          "charge.create",
    "charge.edit_charge":         "charge.edit",
    "charge.delete_charge":       "charge.delete",

    # ── B8, file attachments (CC-2, 2 September 2026) ────────────────────────
    #
    # ⚠ **NO NEW PERMISSION IS MINTED FOR AN ATTACHMENT, deliberately.** Whoever
    #   may view a charge may view the document that charge is evidenced by;
    #   whoever may delete a charge may remove its supporting file. A separate
    #   `attachment.*` family would be four more ids to grant, and a role that
    #   held `charge.view` without it would see a list of files it could not
    #   open — a permission that reaches no role is exactly the failure ABOUT.md
    #   §2g records shipping three times.
    #
    # ⚠ **Three endpoints PER PARENT rather than three in total**, because this
    #   registry maps one endpoint to one permission and an attachment's
    #   permission depends on which record it hangs off. `attachment.py` mints
    #   them from `PARENTS` for exactly that reason; the alternative was one
    #   endpoint classified `AUTHENTICATED` with the real check hidden in the
    #   view, which is the weakening B5 exists to prevent.
    #
    # ⚠ **`delete_*` carries the parent's DELETE permission, not its view one.**
    #   It answers POST only and it destroys a file. A read verb on a writing
    #   POST is §7 gap 24b, and this is the registry caveat that catches it.
    "attachment.view_charge":      "charge.view",
    "attachment.download_charge":  "charge.view",
    "attachment.delete_charge":    "charge.delete",
    "attachment.view_receipt":     "receipt.view",
    "attachment.download_receipt": "receipt.view",
    "attachment.delete_receipt":   "receipt.delete",
    # C4, the employee master. `/employee/delete/<id>` answers both verbs and is
    # classified once, as `employee.delete`: its GET renders a confirmation and
    # destroys nothing, so the stricter of the two permissions is the right one
    # for both. That is the ordinary case this registry's fourth caveat
    # describes, not the `/projects/view/<id>` exception.
    "employee.list_employees":    "employee.view",
    "employee.view_employee":     "employee.view",
    "employee.new_employee":      "employee.create",
    "employee.edit_employee":     "employee.edit",
    "employee.delete_employee":   "employee.delete",

    # ── Attendance and site-wise labour cost (C5) ────────────────────────────
    # `/attendance/delete/<id>` answers both verbs and is classified once, as
    # `attendance.delete`: its GET renders a confirmation and destroys nothing,
    # so the stricter of the two is right for both. The ordinary case this
    # registry's fourth caveat describes, not the `/projects/view/<id>`
    # exception.
    "attendance.list_attendance":  "attendance.view",
    "attendance.mark_attendance":  "attendance.create",
    "attendance.edit_attendance":  "attendance.edit",
    "attendance.delete_attendance": "attendance.delete",

    # ── Approvals (B6) ───────────────────────────────────────────────────────
    # ⚠ **Eight endpoints, not one.** A single `/approval/approve/<doc_key>/<id>`
    # would need four different permissions on one endpoint, which this registry
    # cannot express — it would have to be classified `AUTHENTICATED` with the
    # real check hidden in the view, which is the weakening B5 exists to
    # prevent. `approval.py` registers the eight from one table, so the bodies
    # are still written once.
    #
    # Reject carries the same permission as approve: rejecting is an approval
    # decision, not a lesser one, and the guard that governs both is the same
    # `approval.can_approve()`.
    "approval.approve_charge":    "charge.approve",
    "approval.reject_charge":     "charge.approve",
    "approval.approve_ra":        "ra.approve",
    "approval.reject_ra":         "ra.approve",
    # C3's merged document climbs the same ladder under the same permission —
    # see the note in approval.DOCUMENTS for why it is `ra.approve` and not
    # `invoice.approve`, and for the check that the two reach the same roles.
    "approval.approve_merged_ra": "ra.approve",
    "approval.reject_merged_ra":  "ra.approve",
    "approval.approve_invoice":   "invoice.approve",
    "approval.reject_invoice":    "invoice.approve",
    "approval.approve_purchase":  "purchase.approve",
    "approval.reject_purchase":   "purchase.approve",
    # C2 — minted by the same `approval._register_routes()` loop off the fifth
    # entry in `approval.DOCUMENTS`. A document added to that table with no rows
    # here is unreachable, and `test_access_control.py` fails until they exist.
    "approval.approve_measurement": "measurement.approve",
    "approval.reject_measurement":  "measurement.approve",

    # ── Projects ─────────────────────────────────────────────────────────────
    "project.list_projects":      "project.view",
    "projectview.view_project":   "project.view",
    "project.create_project":     "project.create",
    "project.edit_project":       "project.edit",
    "project.delete_project":     "project.delete",

    # ── Library ──────────────────────────────────────────────────────────────
    "spec.list_specs":            "spec.view",
    "spec.view_spec":             "spec.view",
    "spec.add_spec":              "spec.create",
    "spec.edit_spec":             "spec.edit",
    "spec.delete_spec":           "spec.delete",
    "product.list_products":      "product.view",
    "product.view_product":       "product.view",
    "product.add_product":        "product.create",
    "product.delete_product":     "product.delete",
    "address.list_addresses":     "address.view",
    "address.view_address":       "address.view",
    "address.add_address":        "address.create",
    "address.edit_address":       "address.edit",
    "address.delete_address":     "address.delete",
    # ⚠ Archive and un-archive are `address.delete`, NOT `address.edit`, and no
    #   permission was minted for them. Archiving is what a refused delete
    #   becomes, so the role stopped by the guard has to be the role that can
    #   take the alternative; and pulling an address out of every picker in the
    #   application is a wider act than correcting one field on it. Owner and
    #   Director hold `address.delete`. Sales Manager, Purchase Manager and
    #   Operation Head hold `address.edit` and deliberately do not get this.
    "address.archive_address":    "address.delete",
    "address.unarchive_address":  "address.delete",
}


# =============================================================================
# BUILTIN ROLES  (B3 Owner + B4's six)
# =============================================================================
# ⚠ **CLIENT_CHANGES-2.md carries no per-role permission grid.** B4 names the
# roles and states exactly one restriction — "HR information is restricted from
# Sales, Purchase and Accounts" — plus the rule that a user may hold several.
# Everything else below is a derived starting position, not a client
# instruction, and it is deliberately editable: an Owner changes any of it with
# checkboxes on `/roles/edit`, which is the whole reason B2 puts roles in data.
#
# The one stated restriction is applied literally: `charge.*` is the wages and
# site-expense ledger, so Sales Manager, Purchase Manager and Accountant do not
# carry it. If the client wants his accountant booking wages, that is a
# checkbox and not a deploy.
#
# ⚠ The five role lines the client stated at the 19 August meeting but which
# carry **no 3A/3B/3C tag and appear nowhere in MG/SF/2026-02** — the two
# "visual dashboard" lines, HR editing salary, and the Accountant's employee
# overview and employee management — are **not** built here and no permission
# below stands in for them. See CLIENT_CHANGES-2.md, "Stated by the client, NOT
# in MG/SF/2026-02".

_ALL_PERMS = tuple(PERMISSIONS)

_OPERATIONS = [
    "dashboard.view", "boq.view", "boq.create", "boq.print",
    "ra.view", "ra.create", "ra.edit", "ra.delete", "ra.issue", "ra.cancel", "ra.print",
    # C2. Operations raise and correct the sheet the installation claim is
    # built from; `measurement.approve` is NOT here, because approving is a
    # ladder rung and is granted per role below.
    "measurement.view", "measurement.create", "measurement.edit",
    "measurement.delete", "measurement.print",
    "dc.view", "dc.create", "dc.edit", "dc.delete", "dc.print",
    "po.view", "po.create", "po.edit", "po.delete", "po.print",
    "purchase.view", "purchase.create", "purchase.edit",
    "project.view", "project.create", "project.edit",
    "spec.view", "spec.create", "spec.edit",
    "product.view", "address.view", "address.create", "address.edit",
    "client.view", "receipt.view",
]

BUILTIN_ROLES = {
    # slug: (display name, permissions)
    "owner": (
        "Owner",
        list(_ALL_PERMS),
    ),
    "director": (
        "Director",
        # Admin tier: everything operational, plus user administration and the
        # refusal log — but NOT `admin.roles`. B3 is explicit that a Director
        # "cannot alter role definitions".
        sorted(set(_OPERATIONS + [
            "extractor.view", "quotation.view", "quotation.create", "quotation.edit",
            "proforma.view", "proforma.create", "invoice.view", "invoice.create",
            "receipt.create", "receipt.edit", "receipt.delete", "client.edit",
            "charge.view", "charge.create", "charge.edit", "charge.delete",
            # B6 — the Director rung appears on all four ladders: the first of
            # the charges ladder and one half of the pair on RA / Tax Invoice /
            # PO. CC-2: "Any one Director's approval is sufficient."
            "charge.approve", "ra.approve", "invoice.approve",
            "purchase.approve",
            # C2 — the measurement ladder is the RA ladder (approval.py), so
            # the Director rung appears on it too.
            "measurement.approve",
            # C4. A Director is the Admin tier and sits inside the HR wall —
            # B4 keeps employee information from Sales, Purchase and Accounts,
            # and names none of those three here.
            "employee.view", "employee.create", "employee.edit",
            "employee.delete",
            # C5, on `employee.*`'s terms — see the catalogue note.
            "attendance.view", "attendance.create", "attendance.edit",
            "attendance.delete",
            "project.delete", "spec.delete", "product.create", "product.delete",
            "address.delete", "settings.edit",
            "admin.users", "admin.access_log",
        ])),
    ),
    "operation-head": (
        "Operation Head",
        # B6 — the Operation Head rung is on all four ladders too: the middle of
        # the charges ladder and the other half of the pair on RA / Tax Invoice
        # / PO. ⚠ The role is spelled "Operation Head" here; CC-2 writes
        # "Operations Head". The application's spelling is the one a lookup has
        # to match, and `approval.role_slugs_of()` reads the slug, not the name.
        sorted(set(_OPERATIONS + ["charge.view", "charge.create", "charge.edit",
                                  "charge.approve", "ra.approve",
                                  "invoice.approve", "purchase.approve",
                                  # C2 — the other half of the RA ladder.
                                  "measurement.approve"])),
    ),
    "hr": (
        "HR",
        # ⚠ **HR's real surface arrived on 29 August 2026: the employee master
        #   (C4).** Until then the only employee data in this app was the wages
        #   ledger, and this role was a stand-in for a job rather than the job.
        #
        # `employee.edit` is held deliberately, and the reasoning is worth
        # keeping: a register somebody can read but nobody can maintain is not
        # a master. ⚠ **Nobody may read that as CC-2's untagged "HR — salary
        # editing, inside employee details" having been delivered.** That line
        # carries no 3A/3B/3C tag, appears nowhere in MG/SF/2026-02, and is
        # recorded as an open item. C4 is an employee master carrying salary;
        # it is not a decision about who may change a figure on it.
        # B6 — HR holds `charge.approve` and NOTHING ELSE from the approval
        # set. It is the third and last rung of the charges ladder, and CC-2
        # puts HR on no other ladder: RA / Tax Invoice / PO are Operation Head +
        # Director. Granting the other three "for symmetry" would put HR on
        # documents the client never placed it on.
        ["dashboard.view", "charge.view", "charge.create", "charge.edit",
         "charge.delete", "charge.approve", "address.view",
         "employee.view", "employee.create", "employee.edit",
         "employee.delete",
         # C5. HR keeps the muster for the same reason it keeps the master: a
         # register somebody can read but nobody can maintain is not a
         # register, and attendance is recorded daily by whoever holds the
         # people data.
         "attendance.view", "attendance.create", "attendance.edit",
         "attendance.delete"],
    ),
    "sales-manager": (
        "Sales Manager",
        ["dashboard.view", "quotation.view", "quotation.create", "quotation.edit",
         "proforma.view", "proforma.create", "invoice.view", "invoice.create",
         "client.view", "client.edit", "boq.view", "boq.create", "boq.print",
         "ra.view", "ra.print", "product.view", "spec.view",
         # C2, on `ra.view` / `ra.print`'s terms: a role that may read a claim
         # may read the measurement the claim was built from. It may not raise
         # or approve one.
         "measurement.view", "measurement.print",
         "address.view", "address.create", "address.edit", "project.view"],
    ),
    "purchase-manager": (
        "Purchase Manager",
        ["dashboard.view", "purchase.view", "purchase.create", "purchase.edit",
         "po.view", "po.create", "po.edit", "po.delete", "po.print",
         "dc.view", "dc.create", "dc.edit", "dc.print",
         "boq.view", "product.view", "spec.view",
         "address.view", "address.create", "address.edit", "project.view"],
    ),
    "accountant": (
        "Accountant",
        ["dashboard.view", "receipt.view", "receipt.create", "receipt.edit",
         "receipt.delete", "client.view", "invoice.view", "proforma.view",
         "ra.view", "ra.print", "purchase.view", "boq.view", "project.view",
         # C2, on `ra.view` / `ra.print`'s terms — see the Sales Manager note.
         "measurement.view", "measurement.print"],
    ),
}


# =============================================================================
# RECORDS
# =============================================================================

def users() -> dict:
    return STORE.setdefault("users", {})


def roles() -> dict:
    return STORE.setdefault("roles", {})


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _esc(v) -> str:
    return P.esc(str(v or ""))


def ensure_builtin_roles() -> int:
    """
    Seed the builtin roles. Idempotent — an existing row is left alone.

    Builtin ids are the fixed slugs `role-owner`, `role-director`, … rather than
    `uuid4().hex[:12]`, for the reason `db.py` gives about the other seeders: a
    fixed id makes re-running a no-op, so a manually emptied table refills
    itself instead of accumulating a second Director. Roles created through the
    UI are minted with uuid4 in the ordinary way.

    An existing builtin's `permissions` list is **not** rewritten. Once an Owner
    has edited what Director means, a later restart must not undo it.
    """
    made = 0
    for slug, (name, perms) in BUILTIN_ROLES.items():
        rid = f"role-{slug}"
        if rid in roles():
            continue
        roles()[rid] = {
            "id":          rid,
            "name":        name,
            "permissions": sorted(set(perms)),
            "builtin":     True,
        }
        made += 1
    return made


# ── Reconciliation: the permission a later pass minted and nobody holds ──────
#
# `ensure_builtin_roles()` above is deliberately non-destructive, and that
# correctness has a standing cost: **a permission minted in a later pass never
# reaches a database that already has its roles.** The permission exists in
# code, it exists on a fresh database, and on the owner's live one no role holds
# it — so the feature it guards is unreachable by everybody, the Owner included,
# because `_gate()` has no Owner bypass.
#
# This has now shipped three times: the four `*.approve` permissions (B6),
# `employee.*` / `attendance.*` (C4 / C5) and `measurement.*` (C2). Twice it was
# repaired by a one-off `_role_grants()` copied into a migration script; the
# third time nobody noticed for a day. The three functions below are that repair
# written **once**, as a general reconciliation any later pass can run, and
# `tools/reconcile_role_permissions.py` is its command line.
#
# ⚠ **They report; they do not write.** `apply_drift()` writes and nothing calls
#   it implicitly — no import, no request hook, no `ensure_builtin_roles()`
#   side effect. Granting a permission is a decision about who may do what, and
#   the 30 August 2026 override block forbids taking it silently.


def role_permission_drift(roles_map=None) -> dict:
    """
    `{role_id: [permission, ...]}` — for every **builtin** role, the permissions
    `BUILTIN_ROLES` gives it *in code* that the stored record does not hold.

    Drift in the other direction is deliberately **not** reported. A permission
    a stored role holds and the code does not give it is an Owner's edit at
    `/roles/edit/<id>`, which `ensure_builtin_roles()` exists to preserve;
    reporting it would invite a "reconciliation" that undoes somebody's decision.

    A role in `BUILTIN_ROLES` with no stored record is skipped rather than
    reported — that is `ensure_builtin_roles()`'s job, and it is idempotent.
    """
    store = roles() if roles_map is None else roles_map
    out = {}
    for slug, (_name, perms) in BUILTIN_ROLES.items():
        rid = f"role-{slug}"
        role = store.get(rid)
        if not role:
            continue
        missing = sorted(set(perms) - set(role.get("permissions") or []))
        if missing:
            out[rid] = missing
    return out


def orphan_permissions(roles_map=None) -> list:
    """
    Every id in `PERMISSIONS` that **no stored role holds at all** — sorted.

    This is the symptom the drift above produces, stated in the form that
    matters operationally: a permission here gates a page nobody in the company
    can open. It is computed over *stored* roles rather than `BUILTIN_ROLES`,
    and that distinction is the whole point — over `BUILTIN_ROLES` the answer is
    always empty, because the Owner role is `list(_ALL_PERMS)` and therefore
    holds every permission by construction. Only a real database can drift.

    Custom roles an Owner has created count as holders, exactly like builtins:
    the question is whether *anybody* can reach the page, not whether a builtin
    can.
    """
    store = roles() if roles_map is None else roles_map
    held = set()
    for role in store.values():
        held |= set(role.get("permissions") or [])
    return sorted(set(PERMISSIONS) - held)


def apply_drift(drift, roles_map=None) -> int:
    """
    Grant `{role_id: [permission, ...]}`. Returns the number of (role,
    permission) pairs actually added.

    Additive only — it never removes a permission a role holds, so an Owner's
    own edits survive it for the same reason they survive `ensure_builtin_roles()`.
    Unknown role ids and permissions absent from `PERMISSIONS` are skipped
    rather than invented.
    """
    store = roles() if roles_map is None else roles_map
    granted = 0
    for rid, perms in drift.items():
        role = store.get(rid)
        if not role:
            continue
        have = set(role.get("permissions") or [])
        add = {p for p in perms if p in PERMISSIONS} - have
        if not add:
            continue
        role["permissions"] = sorted(have | add)
        granted += len(add)
    return granted


def find_user(username: str):
    """The user record for `username`, compared case-insensitively, or None."""
    wanted = (username or "").strip().lower()
    if not wanted:
        return None
    for u in users().values():
        if (u.get("username") or "").strip().lower() == wanted:
            return u
    return None


def create_user(username: str, display_name: str, password: str,
                role_ids: list, created_by: str = "", active: bool = True) -> dict:
    """
    Mint a user. Raises ValueError on a blank or duplicate username.

    The username is stored **as entered** and compared **case-insensitively**:
    `Yogesh` and `yogesh` are the same login, and the register shows whichever
    spelling the person actually uses.
    """
    username = (username or "").strip()
    if not username:
        raise ValueError("A username is required.")
    if not (password or ""):
        raise ValueError("A password is required.")
    if find_user(username) is not None:
        raise ValueError(f"The username {username!r} is already taken.")

    uid = uuid.uuid4().hex[:12]
    rec = {
        "id":            uid,
        "username":      username,
        "display_name":  (display_name or "").strip() or username,
        "password_hash": generate_password_hash(password),
        "role_ids":      [r for r in (role_ids or []) if r in roles()],
        "active":        bool(active),
        "created_at":    _now(),
        "created_by":    created_by or "",
    }
    users()[uid] = rec
    return rec


def permissions_of(user) -> set:
    """
    The **union** of every role the user holds (B2, B4).

    Resolved from the store on each call rather than cached on the session, so
    a role edit lands on the user's next request.
    """
    if not user:
        return set()
    out = set()
    for rid in user.get("role_ids") or []:
        role = roles().get(rid)
        if role:
            out.update(role.get("permissions") or [])
    return out & set(PERMISSIONS)


def is_owner(user) -> bool:
    """B3's Owner tier: the right to define what a role means."""
    return OWNER_PERM in permissions_of(user)


def active_owners() -> list:
    return [u for u in users().values() if u.get("active") and is_owner(u)]


def _role_names(user) -> str:
    names = [roles()[r]["name"] for r in (user.get("role_ids") or []) if r in roles()]
    return ", ".join(sorted(names)) or "—"


# =============================================================================
# SESSION
# =============================================================================

def current_user():
    """
    The logged-in user, or None.

    An account deactivated mid-session resolves to None on the very next
    request — which is what makes "urgent access removal when someone is
    dismissed" (B3) actually immediate rather than effective at next login.
    """
    uid = session.get(SESSION_KEY)
    if not uid:
        return None
    user = users().get(uid)
    if not user or not user.get("active"):
        return None
    return user


def has_perm(perm: str) -> bool:
    return perm in permissions_of(current_user())


def login_user(user) -> None:
    session.clear()
    session[SESSION_KEY] = user["id"]
    session.permanent = True


def logout_user() -> None:
    session.clear()


# =============================================================================
# THE REFUSAL LOG
# =============================================================================
# Every refusal is recorded with who, what and which permission was wanted.
#
# This is the surviving half of CLIENT_CHANGES-2.md B5's audit mode. B5 asks for
# a two-stage rollout — log without blocking, then flip to enforce — and this
# pass enforces from the start instead (recorded as a deviation in the 26 August
# 2026 override block in CLIENT_CHANGES.md §0). The enumeration test replaces
# stage one's main job: it proves no endpoint is unclassified *before* the hook
# goes live. What it cannot see is a route classified **wrongly** — a permission
# scoped too tight, so a real user is blocked doing their job — and that is
# exactly what this log is for. Block and log.
#
# In memory and bounded: this is a diagnostic, not a record. It is deliberately
# NOT a persisted collection — an audit trail with retention and immutability is
# a different feature, and pretending a ring buffer is one would be worse than
# not having it (ABOUT.md §7 gap 23). Refusals also go to `app.logger` so they
# survive a restart in the ordinary server log.

REFUSAL_LOG = deque(maxlen=500)


def _log_refusal(user, endpoint: str, permission, reason: str) -> None:
    entry = {
        "at":         _now(),
        "user":       (user or {}).get("username") or "(anonymous)",
        "user_id":    (user or {}).get("id") or "",
        "endpoint":   endpoint or "(unmatched)",
        "path":       request.path,
        "method":     request.method,
        "permission": permission if isinstance(permission, str) else "(none)",
        "reason":     reason,
    }
    REFUSAL_LOG.appendleft(entry)
    try:
        from flask import current_app
        current_app.logger.warning(
            "access refused: user=%s endpoint=%s permission=%s reason=%s path=%s",
            entry["user"], entry["endpoint"], entry["permission"],
            entry["reason"], entry["path"])
    except Exception:
        pass


# =============================================================================
# THE GATE  (B5)
# =============================================================================

def _safe_next(raw: str) -> str:
    """
    A `next=` target that cannot leave this site.

    Anything not starting with a single `/` is discarded — `//evil.test` and
    `https://evil.test` both fail — so the login form cannot be turned into an
    open redirect by a crafted link.
    """
    raw = (raw or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return ""


def _gate():
    """
    Default deny, in one place, on every request.

    Runs as a `before_request` hook. Returning None lets the request through;
    returning a response refuses it.

    Order matters. An **unregistered** endpoint is refused before the session is
    even consulted, because that is a configuration fault rather than an
    authentication one and the honest answer is 403 for everybody — including an
    Owner, who would otherwise be the one person who never notices.
    """
    endpoint = request.endpoint
    if endpoint is None:
        # No rule matched. Leave it to the 404 handler, which redirects to the
        # dashboard — itself gated, so an anonymous stranger still lands on the
        # login page rather than anywhere useful.
        return None

    required = ROUTE_PERMISSIONS.get(endpoint)

    if required is None:
        _log_refusal(current_user(), endpoint, None, "endpoint not in the registry")
        return _refusal_page(
            "This page has no permission declared",
            "Access control in this application is default-deny: a route that has "
            "not been classified is refused rather than opened. Nobody can reach "
            "this page, including an Owner. It needs an entry in "
            "<code>auth.ROUTE_PERMISSIONS</code>."), 403

    if required == PUBLIC:
        return None

    user = current_user()
    if user is None:
        # Bootstrap: with no users at all, the login form has nothing to check
        # against, so the first run goes to /setup instead of a dead end.
        if not users():
            return redirect(url_for("auth.setup"))
        _log_refusal(None, endpoint, required, "no session")
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    if required == AUTHENTICATED:
        return None

    if required not in permissions_of(user):
        _log_refusal(user, endpoint, required, "permission not held")
        label = PERMISSIONS.get(required, (required, ""))[0]
        return _refusal_page(
            "You do not have access to this page",
            f"It needs the <b>{_esc(label)}</b> permission "
            f"(<code>{_esc(required)}</code>), which none of your roles carries. "
            f"Ask an administrator to add it to one of them."), 403

    return None


def can_reach(endpoint: str, user=None) -> bool:
    """
    Would `_gate()` let this user through to `endpoint`?

    **Navigation asks this; it never decides anything.** Every menu entry and
    every dashboard card is drawn only when this returns True, so a user is not
    shown a door that will slam — but the door is still locked by `_gate()`,
    which runs on the request regardless of what was drawn. Hiding is
    presentation. If a check anywhere starts looking redundant because a link is
    gone, that is the bug: the link is one `curl` away from being back.

    **It reads `ROUTE_PERMISSIONS`, the same dict the gate reads**, and it is
    written to mirror `_gate()`'s branches in the same order. That is the whole
    point — a second hand-maintained list of "what to show" drifts from the list
    of "what to allow", and every drift is either a dead link or a hidden route
    that is quietly open.
    `tests/test_nav_visibility.py::test_can_reach_agrees_with_the_gate_on_every_endpoint_for_every_role`
    sweeps all 7 builtin roles against every classified endpoint and fails on
    any disagreement, so the mirroring is asserted rather than maintained by
    memory.

    Absence is False, exactly as absence is a refusal in the gate: an
    unclassified endpoint is unreachable, so a launcher must not offer it.
    """
    required = ROUTE_PERMISSIONS.get(endpoint)
    if required is None:
        return False
    if required == PUBLIC:
        return True

    user = current_user() if user is None else user
    if user is None:
        return False
    if required == AUTHENTICATED:
        return True
    return required in permissions_of(user)


def install(app) -> None:
    """
    The identity layer: real signing key, session lifetime, builtin roles.

    Called from `app.py` after the blueprints are registered. On its own this
    changes nothing about who can reach what — it makes login *possible*.
    `enforce()` is what makes it *required*, and the two are separate functions
    so that the commit which turns access control on is one line and one revert.
    """
    key, source = resolve_secret_key_with_source()
    app.secret_key = key
    # ⚠ Loud, and only when nobody supplied a key. It goes to **stderr** so a
    #   deployment that pipes stdout to a log still puts it in front of whoever
    #   started the process, and it never raises — see `secret_key_warning()`.
    warning = secret_key_warning(source)
    if warning:
        print(warning, file=sys.stderr, flush=True)
    app.permanent_session_lifetime = datetime.timedelta(hours=SESSION_HOURS)
    ensure_builtin_roles()


def enforce(app) -> None:
    """
    Turn default deny on.

    Everything before this line is inert plumbing; this is the line that closes
    the application. Kept separate from `install()` so reverting the commit that
    added it restores open access without losing users, roles or the pages that
    manage them.
    """
    app.before_request(_gate)


# =============================================================================
# STYLES
# =============================================================================
# Plain string constants, not f-strings — so the CSS braces here need no
# doubling. That only applies to the f-string page bodies further down, which
# is why none of them contains a literal brace.

# `/login` and `/setup` are reached while logged out, so they carry no nav: the
# nav links to Projects and Settings, both of which would refuse. They are the
# only two pages in the app that do not layer `dashboard.BASE_STYLES`, and both
# are named with that reason in `tests/test_page_chrome.py::NO_CHROME`.
AUTH_STANDALONE_STYLES = """
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; background: #f4f5f7;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1f2430; padding: 1.5rem;
  }
  .auth-card {
    width: 100%; max-width: 380px; background: #fff; border-radius: 10px;
    border: 1px solid #e2e5ea; box-shadow: 0 6px 24px rgba(20,25,40,.08);
    padding: 2rem 1.75rem;
  }
  .auth-brand { text-align: center; margin-bottom: 1.5rem; }
  .auth-brand img { height: 42px; }
  .auth-brand h1 { font-size: 1.15rem; margin: .75rem 0 .25rem; }
  .auth-brand p { margin: 0; font-size: .8rem; color: #6b7280; }
  .auth-card label {
    display: block; font-size: .78rem; font-weight: 600; color: #414957;
    margin-bottom: .3rem; text-transform: uppercase; letter-spacing: .03em;
  }
  .auth-card input[type=text], .auth-card input[type=password] {
    width: 100%; padding: .6rem .7rem; margin-bottom: 1rem; font-size: .95rem;
    border: 1px solid #d3d8e0; border-radius: 6px; background: #fdfdfe;
  }
  .auth-card input:focus { outline: 2px solid #c62828; outline-offset: 1px; }
  .auth-btn {
    width: 100%; padding: .65rem; font-size: .95rem; font-weight: 600;
    color: #fff; background: #c62828; border: 0; border-radius: 6px;
    cursor: pointer;
  }
  .auth-btn:hover { background: #a81f1f; }
  .auth-err, .auth-note {
    padding: .6rem .75rem; border-radius: 6px; font-size: .85rem;
    margin-bottom: 1rem;
  }
  .auth-err  { background: #fdecec; border: 1px solid #f5c2c2; color: #8c1c1c; }
  .auth-note { background: #eef4fd; border: 1px solid #c9dcf6; color: #1c4e8c; }
  .auth-foot { margin-top: 1.25rem; font-size: .75rem; color: #8b93a1; text-align: center; }
</style>
"""

AUTH_ADMIN_STYLES = """
<style>
  .auth-table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  .auth-table th {
    text-align: left; padding: .55rem .5rem; font-size: .78rem;
    text-transform: uppercase; letter-spacing: .03em;
    border-bottom: 2px solid var(--border);
  }
  .auth-table td {
    padding: .55rem .5rem; font-size: .88rem;
    border-bottom: 1px solid var(--border); vertical-align: top;
  }
  .auth-table tr:nth-child(even) { background: var(--surface); }
  .au-off { opacity: .55; }
  .au-tag {
    display: inline-block; padding: .1rem .45rem; border-radius: 10px;
    font-size: .72rem; font-weight: 600; background: #eef1f5; color: #48505e;
    margin: 0 .25rem .25rem 0;
  }
  .au-tag.owner { background: #fdecec; color: #8c1c1c; }
  .au-tag.on    { background: #e8f5e9; color: #1b5e20; }
  .au-tag.off   { background: #f2f3f5; color: #6b7280; }
  .perm-group { margin: 0 0 1.1rem; border: 1px solid var(--border); border-radius: 8px; }
  .perm-group > h4 {
    margin: 0; padding: .5rem .75rem; font-size: .8rem; background: var(--surface);
    border-bottom: 1px solid var(--border); text-transform: uppercase;
    letter-spacing: .03em;
  }
  .perm-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: .35rem .9rem; padding: .75rem;
  }
  .perm-grid label { font-size: .85rem; display: flex; gap: .45rem; align-items: baseline; }
  .perm-grid code { font-size: .74rem; color: #8b93a1; }
  .auth-form label.fld {
    display: block; font-size: .78rem; font-weight: 600; margin: .9rem 0 .3rem;
    text-transform: uppercase; letter-spacing: .03em;
  }
  .auth-form input[type=text], .auth-form input[type=password] {
    width: 100%; max-width: 420px; padding: .55rem .65rem; font-size: .92rem;
    border: 1px solid var(--border); border-radius: 6px;
  }
  .role-pick { display: flex; flex-wrap: wrap; gap: .4rem .9rem; }
  .role-pick label { font-size: .88rem; display: flex; gap: .4rem; align-items: baseline; }
  .log-tbl td { font-size: .82rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
"""


# =============================================================================
# PAGE SHELLS
# =============================================================================

def _standalone(title: str, body: str) -> str:
    """A logged-out page: brand, card, no nav."""
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {AUTH_STANDALONE_STYLES}
</head>
<body>
  <div class="auth-card">
    <div class="auth-brand">
      {B.logo_img(42)}
      <h1>{_esc(B.COMPANY_NAME)}</h1>
      <p>{_esc(B.APP_SUBTITLE)}</p>
    </div>
    {body}
    <p class="auth-foot">{_esc(title)}</p>
  </div>
</body></html>"""


def _shell(title: str, body: str) -> str:
    """
    An administration page, with the app's ordinary chrome.

    `dashboard` is imported **inside the function body**: it imports this module
    to decide whether to draw the Access card, so a module-level import here
    would be a cycle. Same escape hatch `dashboard.index()` uses for the
    `product` and `address` seeders (ABOUT.md §2).
    """
    from dashboard import BASE_STYLES, _nav
    from quotation import QUOTATION_STYLES
    return f"""<!DOCTYPE html><html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{B.page_title(title)}</title>{B.HEAD_ICON}
  {BASE_STYLES}{QUOTATION_STYLES}{AUTH_ADMIN_STYLES}
</head>
<body>
{_nav()}
<main>
{body}
</main>
</body></html>"""


def _refusal_page(heading: str, detail: str) -> str:
    """
    Why this was refused, in words, on the page.

    INTRODUCTION.md §2: "a rule this system enforces has to state its reason on
    the page, in words, at the moment it fires — an error that says only
    'invalid' costs somebody an afternoon." A bare 403 is exactly that error.
    """
    body = f"""
    <div class="card" style="max-width:640px;margin:2rem auto;">
      <h2 style="margin-top:0;">{_esc(heading)}</h2>
      <p>{detail}</p>
      <p style="margin-bottom:0;">
        <a class="btn" href="{url_for('dashboard.index')}">Back to the dashboard</a>
      </p>
    </div>"""
    try:
        return _shell("Access refused", body)
    except Exception:
        # The chrome import can only fail during a partially-initialised app.
        # A refusal must still refuse, so fall back to the standalone sheet.
        return _standalone("Access refused", body)


def _alert() -> str:
    msg = (request.args.get("msg") or "").strip()
    if not msg:
        return ""
    kind = "alert-success" if request.args.get("type") == "success" else "alert-error"
    return f'<div class="alert {kind}">{_esc(msg)}</div>'


# =============================================================================
# ROUTES — session
# =============================================================================

# A hash of a value nobody holds, minted once at import. `login()` verifies the
# submitted password against this when the username does not exist, so that the
# not-found path costs the same scrypt work as the found path and the response
# time stops saying whether an account is real. It can never match: the input is
# 32 random bytes that are discarded immediately.
#
# Generated rather than hardcoded on purpose — a literal hash in this file would
# be a published value, and `tests/test_auth.py` reads every module's AST to
# keep exactly that kind of constant out of the codebase.
_DUMMY_HASH = generate_password_hash(secrets.token_hex(32))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """The one public page that grants a session."""
    if not users():
        return redirect(url_for("auth.setup"))

    nxt = _safe_next(request.values.get("next", ""))
    error = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = find_user(username)

        # One message for every failure. Distinguishing "no such user" from
        # "wrong password" tells an attacker which half to keep working on.
        #
        # ⚠ **The message was never the leak. The clock was.**
        # `check_password_hash` is scrypt and costs ~70 ms; it only ran when
        # `find_user()` returned a record, so an unknown username was answered
        # in ~0.3 ms and a real one in ~70 ms — **239x**, measured. That is not
        # a side channel needing statistics to see: it is visible in a
        # browser's network tab, over the internet, on the first attempt, and
        # it enumerates every valid username in this install however carefully
        # the page is worded. Paired with §7 gap 22 (no rate limit, no
        # lockout) it turns password guessing from "guess a name and a
        # password" into "guess a password for a name you know is real".
        #
        # So the not-found path pays the same cost: hash the supplied password
        # against a fixed dummy and throw the answer away. `_DUMMY_HASH` is
        # minted once at import from a random value nobody holds, so it can
        # never match anything.
        if user is None:
            check_password_hash(_DUMMY_HASH, password)

        if (user is None
                or not check_password_hash(user.get("password_hash") or "", password)):
            error = "That username and password do not match."
        elif not user.get("active"):
            # Said plainly on purpose: a dismissed employee's own account is not
            # a secret from them, and "wrong password" would send an honest user
            # off resetting a password that is not the problem.
            error = "That account has been deactivated. Ask an administrator."
        else:
            login_user(user)
            return redirect(nxt or url_for("dashboard.index"))

    err_html = f'<div class="auth-err">{_esc(error)}</div>' if error else ""
    nxt_html = f'<input type="hidden" name="next" value="{_esc(nxt)}"/>' if nxt else ""
    body = f"""
    {err_html}
    <form method="post">
      {nxt_html}
      <label for="username">Username</label>
      <input id="username" name="username" type="text" autocomplete="username"
             autofocus required
             value="{_esc(request.form.get('username', '') if request.method == 'POST' else '')}"/>
      <label for="password">Password</label>
      <input id="password" name="password" type="password"
             autocomplete="current-password" required/>
      <button class="auth-btn" type="submit">Sign in</button>
    </form>"""
    return _standalone("Sign in", body)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """
    GET confirms, POST destroys.

    The same shape as every delete route in this app, set in commit `9d060ee`
    and swept by `tests/test_delete_methods.py`. A GET that ends a session is
    triggered by a link prefetcher, a crawler or a mail scanner unfurling the
    URL — all of which would quietly log the user out mid-form.
    """
    if request.method == "POST":
        logout_user()
        return redirect(url_for("auth.login", msg="You have been signed out.",
                                type="success"))

    user = current_user()
    if user is None:
        # Reachable when the gate is not installed, and after a session expires
        # between the page loading and the form posting. These two views are the
        # only ones that read `current_user()` without a permission behind them,
        # so they are the only two that have to say so themselves.
        return redirect(url_for("auth.login"))
    body = f"""
    <div class="card" style="max-width:520px;margin:2rem auto;">
      <h2 style="margin-top:0;">Sign out</h2>
      <p>You are signed in as <b>{_esc(user.get('display_name'))}</b>
         ({_esc(user.get('username'))}).</p>
      <form method="post" style="display:flex;gap:.6rem;align-items:center;">
        <button class="btn" type="submit">Sign out</button>
        <a href="{url_for('dashboard.index')}">Stay signed in</a>
      </form>
    </div>"""
    return _shell("Sign out", body)


@auth_bp.route("/account", methods=["GET", "POST"])
def account():
    """Own details, and the only place a user changes their own password."""
    user = current_user()
    if user is None:
        return redirect(url_for("auth.login", next=url_for("auth.account")))
    msg = kind = ""

    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        if not check_password_hash(user.get("password_hash") or "", current):
            msg, kind = "Your current password is not correct.", "alert-error"
        elif len(new) < 8:
            msg, kind = "The new password must be at least 8 characters.", "alert-error"
        elif new != confirm:
            msg, kind = "The two new passwords do not match.", "alert-error"
        else:
            user["password_hash"] = generate_password_hash(new)
            msg, kind = "Your password has been changed.", "alert-success"

    perms = sorted(permissions_of(user))
    perm_rows = "".join(
        f'<span class="au-tag">{_esc(PERMISSIONS[p][0])}</span>' for p in perms)
    note = f'<div class="alert {kind}">{_esc(msg)}</div>' if msg else ""
    owner_tag = '<span class="au-tag owner">Owner</span>' if is_owner(user) else ""

    body = f"""
    {note}
    <div class="card" style="max-width:720px;">
      <h2 style="margin-top:0;">My account</h2>
      <p><b>{_esc(user.get('display_name'))}</b> &middot;
         {_esc(user.get('username'))} {owner_tag}</p>
      <p>Roles: {_esc(_role_names(user))}</p>
      <details style="margin:.75rem 0;">
        <summary>What I can do &mdash; {len(perms)} permissions</summary>
        <div style="margin-top:.6rem;">{perm_rows}</div>
      </details>
      <hr/>
      <h3>Change my password</h3>
      <p style="font-size:.85rem;color:#6b7280;">
        There is no e-mail password reset &mdash; it is out of scope by
        agreement. If you are locked out, an Owner sets a new password for you.
      </p>
      <form method="post" class="auth-form">
        <label class="fld" for="cur">Current password</label>
        <input id="cur" name="current_password" type="password"
               autocomplete="current-password" required/>
        <label class="fld" for="new">New password</label>
        <input id="new" name="new_password" type="password"
               autocomplete="new-password" required/>
        <label class="fld" for="cnf">Confirm new password</label>
        <input id="cnf" name="confirm_password" type="password"
               autocomplete="new-password" required/>
        <p><button class="btn" type="submit">Change password</button></p>
      </form>
    </div>"""
    return _shell("My account", body)


# =============================================================================
# ROUTES — first-run setup
# =============================================================================

@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """
    The first Owner, created in a browser.

    Public **only while `users` is empty**. The moment one exists this redirects,
    so the window closes by itself rather than depending on somebody remembering
    to close it. `tools/seed_users.py` is the same job non-interactively.
    """
    if users():
        return redirect(url_for("auth.login"))

    ensure_builtin_roles()
    error = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        display = (request.form.get("display_name") or "").strip()
        pw = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        if not username:
            error = "A username is required."
        elif len(pw) < 8:
            error = "The password must be at least 8 characters."
        elif pw != confirm:
            error = "The two passwords do not match."
        else:
            user = create_user(username, display, pw,
                               ["role-owner", "role-director"], created_by="setup")
            login_user(user)
            return redirect(url_for("dashboard.index"))

    err_html = f'<div class="auth-err">{_esc(error)}</div>' if error else ""
    body = f"""
    {err_html}
    <div class="auth-note">
      No users exist yet. This creates the first <b>Owner</b> &mdash; the account
      that defines what every other role means. This page stops working as soon
      as it succeeds.
    </div>
    <form method="post">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" autofocus required
             autocomplete="username"/>
      <label for="display_name">Full name</label>
      <input id="display_name" name="display_name" type="text"/>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" required
             autocomplete="new-password"/>
      <label for="confirm_password">Confirm password</label>
      <input id="confirm_password" name="confirm_password" type="password" required
             autocomplete="new-password"/>
      <button class="auth-btn" type="submit">Create the Owner account</button>
    </form>"""
    return _standalone("First-run setup", body)


# =============================================================================
# GUARDS — B3's two lockout invariants
# =============================================================================

def _may_grant(actor, role_ids) -> str:
    """
    "" when `actor` may assign exactly this set of roles, else the refusal.

    B3: *only an Owner can create an Owner.* Without this an Admin could pick
    the Owner role off the same checkbox list that assigns Sales Manager, and
    the tier split would be decoration — the Admin who "cannot alter role
    definitions" would simply grant themselves the role that can.

    ⚠ **The rule is wider than the Owner role, and used to be written narrower
    than it.** Until 27 August 2026 this checked one permission — `admin.roles`
    — so it happened to be correct only because the Director role is the one
    the client has, and `admin.roles` is the only permission a Director lacks.
    The moment an Owner uses B2 as intended and bundles a *limited* admin role
    — `admin.users` plus a handful of operational permissions, which is the
    whole point of roles being data — that holder could hand somebody else the
    HR role and confer `charge.delete`, a permission they do not hold and
    cannot exercise. **Nobody confers what they do not hold**, so the test is
    now the whole permission set of each role against the actor's own union.
    """
    if is_owner(actor):
        return ""
    held = permissions_of(actor)
    for rid in role_ids or []:
        role = roles().get(rid)
        if not role:
            continue
        carried = set(role.get("permissions") or []) & set(PERMISSIONS)
        if OWNER_PERM in carried:
            return (f"Only an Owner can grant the {role['name']!r} role, because "
                    f"it carries the right to change what every other role means.")
        missing = sorted(carried - held)
        if missing:
            return (f"You cannot grant the {role['name']!r} role: it carries "
                    f"{_perm_phrase(missing)}, which you do not hold yourself. A "
                    f"permission you do not have cannot be given to somebody else.")
    return ""


def _perm_phrase(perm_ids) -> str:
    """Up to three permission labels in words, then a count. Display only."""
    shown = [PERMISSIONS[p][0] for p in perm_ids[:3] if p in PERMISSIONS]
    tail = f" and {len(perm_ids) - 3} more" if len(perm_ids) > 3 else ""
    return ", ".join(shown) + tail


def _may_administer(actor, target) -> str:
    """
    "" when `actor` may change this account, else the refusal.

    The mirror of `_may_grant()`, and the half that was missing.

    `_may_grant()` guards the **roles** field on `/users/create` and
    `/users/edit`. Nothing guarded the **password** field beside it, and
    `/users/edit` sets a password for any account it can load — so a Director,
    who holds `admin.users` and may not create an Owner, could instead set the
    existing Owner's password and sign in as them. That reaches the same place
    by a shorter route: it needs no role change at all, and the account it
    lands in is the one B3 calls undeletable. Measured on 27 August 2026 — the
    forged sign-in reached `/roles` with a 200.

    So the rule is symmetric. Conferring a permission you do not hold is
    refused; **taking over an account that holds one is the same act** and is
    refused too. An Owner short-circuits, exactly as in `_may_grant()`: the
    Owner tier can already grant itself anything by editing a role, so testing
    them against a subset would only produce a puzzling refusal if somebody
    ever unticks a permission on the Owner role.

    Acting on your own account is always allowed — you gain nothing you did not
    already have, and `/account` is the ordinary way to change your own
    password anyway. `_would_strand_install()` still guards the one thing you
    can do to yourself that matters.
    """
    if is_owner(actor):
        return ""
    if not target or (actor or {}).get("id") == target.get("id"):
        return ""

    extra = sorted(permissions_of(target) - permissions_of(actor))
    if not extra:
        return ""
    if OWNER_PERM in extra:
        return ("This is an Owner account, and you are not an Owner. Setting its "
                "password would let you sign in as it, and taking its roles away "
                "would decide who administers this install — both are the Owner "
                "tier, which none of your roles carries.")
    return (f"This account holds {_perm_phrase(extra)}, which you do not hold "
            f"yourself. Setting its password would let you sign in as it, so only "
            f"somebody who already holds everything it does may change it.")


def _administer_refusal(target):
    """
    The 403 for `_may_administer()`, or None when the change is allowed.

    Returned as a refusal page rather than a form error because that is what it
    is: the same shape `_gate()` returns, logged to the same place, so it shows
    up on `/access-log` beside every other refusal instead of being invisible
    outside the browser it happened in.
    """
    actor = current_user()
    detail = _may_administer(actor, target)
    if not detail:
        return None
    _log_refusal(actor, request.endpoint, None,
                 "the target account holds permissions the actor does not")
    return _refusal_page("You cannot administer this account", _esc(detail)), 403


def _would_strand_install(user_id: str, new_role_ids=None, deactivating=False) -> str:
    """
    "" when the change is safe, else the refusal.

    B3: *the last remaining Owner cannot be deleted or deactivated.* Extended
    here to cover the equivalent through the side door — an Owner editing their
    own roles down to something that no longer carries `admin.roles`. Both end
    with an install nobody can administer, and the second is the easier one to
    do by accident.
    """
    owners = active_owners()
    if len(owners) > 1 or not any(o["id"] == user_id for o in owners):
        return ""

    if deactivating:
        return ("This is the only active Owner. Deactivating it would leave nobody "
                "able to define roles. Give another user an Owner role first.")

    if new_role_ids is not None:
        keeps_owner = any(OWNER_PERM in (roles().get(r, {}).get("permissions") or [])
                          for r in new_role_ids)
        if not keeps_owner:
            return ("This is the only active Owner. Removing that role would leave "
                    "nobody able to define roles. Give another user an Owner role "
                    "first.")
    return ""


def _role_edit_refusal(role: dict, perms: list) -> str:
    """
    "" when a role may be saved with `perms`, else the refusal.

    Two floors, both about not bricking the install with one checkbox:

    * the **Owner** role keeps `admin.roles` — it is the only role that can put
      the permission back once it is gone;
    * the **Director** role keeps `admin.users`, because B3 gives the client's
      own Directors the user administration, and a Director who cannot add a
      user has to phone us to hire somebody.
    """
    if role.get("id") == "role-owner" and OWNER_PERM not in perms:
        return ("The Owner role must keep 'Define what a role means'. It is the "
                "only role that can grant that permission back, so removing it "
                "would leave no way to edit any role again.")
    if role.get("id") == "role-director" and ADMIN_PERM not in perms:
        return ("The Director role must keep 'Create, edit and deactivate users'. "
                "Directors administer users in this install by agreement, and a "
                "Director who cannot add one has no way to restore access.")
    return ""


# =============================================================================
# ROUTES — users
# =============================================================================

@auth_bp.route("/users")
def list_users():
    rows = []
    for u in sorted(users().values(), key=lambda r: (not r.get("active"),
                                                     (r.get("username") or "").lower())):
        state = ('<span class="au-tag on">active</span>' if u.get("active")
                 else '<span class="au-tag off">deactivated</span>')
        owner = '<span class="au-tag owner">Owner</span>' if is_owner(u) else ""
        if u.get("active"):
            act = (f'<a href="{url_for("auth.edit_user", id=u["id"])}">Edit</a> &middot; '
                   f'<a href="{url_for("auth.deactivate_user", id=u["id"])}">Deactivate</a>')
        else:
            act = (f'<a href="{url_for("auth.edit_user", id=u["id"])}">Edit</a> &middot; '
                   f'<a href="{url_for("auth.activate_user", id=u["id"])}">Reactivate</a>')
        rows.append(f"""
        <tr class="{'' if u.get('active') else 'au-off'}">
          <td><b>{_esc(u.get('display_name'))}</b><br/>
              <span style="font-size:.8rem;color:#6b7280;">{_esc(u.get('username'))}</span></td>
          <td>{_esc(_role_names(u))} {owner}</td>
          <td>{state}</td>
          <td style="font-size:.8rem;color:#6b7280;">{_esc(u.get('created_at'))}</td>
          <td>{act}</td>
        </tr>""")

    empty = ('<tr><td colspan="5" style="padding:1.5rem;text-align:center;color:#6b7280;">'
             'No users yet.</td></tr>')
    body = f"""
    {_alert()}
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  flex-wrap:wrap;gap:.75rem;">
        <h2 style="margin:0;">Users</h2>
        <div style="display:flex;gap:.5rem;">
          <a class="btn" href="{url_for('auth.create_user')}">+ New user</a>
          <a class="btn" href="{url_for('auth.list_roles')}">Roles</a>
          {_access_log_link()}
        </div>
      </div>
      <p style="font-size:.85rem;color:#6b7280;margin:.6rem 0 0;">
        Users are never deleted, only deactivated &mdash; every record they
        created still names them.
      </p>
      <table class="auth-table">
        <thead><tr><th>User</th><th>Roles</th><th>State</th><th>Created</th><th></th></tr></thead>
        <tbody>{''.join(rows) or empty}</tbody>
      </table>
    </div>"""
    return _shell("Users", body)


def _role_checkboxes(selected) -> str:
    picked = set(selected or [])
    out = []
    for r in sorted(roles().values(), key=lambda x: x["name"]):
        mark = " checked" if r["id"] in picked else ""
        owner = " (Owner)" if OWNER_PERM in (r.get("permissions") or []) else ""
        out.append(f'<label><input type="checkbox" name="role_ids" '
                   f'value="{_esc(r["id"])}"{mark}/>{_esc(r["name"] + owner)}</label>')
    return f'<div class="role-pick">{"".join(out)}</div>'


# The endpoint is pinned to `auth.create_user` rather than being derived from
# the function name: `create_user` is already the record helper above, so the
# view is `create_user_route` while `ROUTE_PERMISSIONS`, the tests and every
# `url_for` here go on saying `auth.create_user`.
@auth_bp.route("/users/create", methods=["GET", "POST"], endpoint="create_user")
def create_user_route():
    error = ""
    form = {"username": "", "display_name": "", "role_ids": []}

    if request.method == "POST":
        form["username"] = (request.form.get("username") or "").strip()
        form["display_name"] = (request.form.get("display_name") or "").strip()
        form["role_ids"] = request.form.getlist("role_ids")
        pw = request.form.get("password") or ""

        error = _may_grant(current_user(), form["role_ids"])
        if not error and len(pw) < 8:
            error = "The password must be at least 8 characters."
        if not error:
            try:
                create_user(form["username"], form["display_name"], pw,
                            form["role_ids"],
                            created_by=(current_user() or {}).get("id", ""))
                return redirect(url_for("auth.list_users",
                                        msg=f"User {form['username']} created.",
                                        type="success"))
            except ValueError as exc:
                error = str(exc)

    err = f'<div class="alert alert-error">{_esc(error)}</div>' if error else ""
    body = f"""
    {err}
    <div class="card" style="max-width:720px;">
      <h2 style="margin-top:0;">New user</h2>
      <form method="post" class="auth-form">
        <label class="fld" for="u">Username</label>
        <input id="u" name="username" type="text" required
               value="{_esc(form['username'])}"/>
        <label class="fld" for="d">Full name</label>
        <input id="d" name="display_name" type="text"
               value="{_esc(form['display_name'])}"/>
        <label class="fld" for="p">Password</label>
        <input id="p" name="password" type="password" required
               autocomplete="new-password"/>
        <label class="fld">Roles &mdash; permissions are the union of all of them</label>
        {_role_checkboxes(form['role_ids'])}
        <p style="margin-top:1.2rem;">
          <button class="btn" type="submit">Create user</button>
          <a href="{url_for('auth.list_users')}" style="margin-left:.6rem;">Cancel</a>
        </p>
      </form>
    </div>"""
    return _shell("New user", body)


@auth_bp.route("/users/edit/<id>", methods=["GET", "POST"])
def edit_user(id):
    user = users().get(id)
    if not user:
        return redirect(url_for("auth.list_users", msg="No such user.", type="error"))

    # Before the form is read, and before it is even drawn: this page sets a
    # password, and a password on a more-privileged account is that account.
    refused = _administer_refusal(user)
    if refused:
        return refused

    error = ""
    if request.method == "POST":
        display = (request.form.get("display_name") or "").strip()
        role_ids = [r for r in request.form.getlist("role_ids") if r in roles()]
        pw = request.form.get("password") or ""

        error = _may_grant(current_user(), set(role_ids) - set(user.get("role_ids") or []))
        if not error:
            error = _would_strand_install(id, new_role_ids=role_ids)
        if not error and pw and len(pw) < 8:
            error = "The password must be at least 8 characters."
        if not error:
            user["display_name"] = display or user["username"]
            user["role_ids"] = role_ids
            if pw:
                user["password_hash"] = generate_password_hash(pw)
            return redirect(url_for("auth.list_users",
                                    msg=f"User {user['username']} updated.",
                                    type="success"))

    err = f'<div class="alert alert-error">{_esc(error)}</div>' if error else ""
    body = f"""
    {err}
    <div class="card" style="max-width:720px;">
      <h2 style="margin-top:0;">Edit {_esc(user.get('username'))}</h2>
      <form method="post" class="auth-form">
        <label class="fld" for="d">Full name</label>
        <input id="d" name="display_name" type="text"
               value="{_esc(user.get('display_name'))}"/>
        <label class="fld" for="p">Set a new password &mdash; leave blank to keep the current one</label>
        <input id="p" name="password" type="password" autocomplete="new-password"/>
        <label class="fld">Roles</label>
        {_role_checkboxes(user.get('role_ids'))}
        <p style="margin-top:1.2rem;">
          <button class="btn" type="submit">Save</button>
          <a href="{url_for('auth.list_users')}" style="margin-left:.6rem;">Cancel</a>
        </p>
      </form>
    </div>"""
    return _shell("Edit user", body)


def _state_change_page(user, verb: str, detail: str, action_url: str) -> str:
    body = f"""
    <div class="card" style="max-width:560px;margin:1.5rem auto;">
      <h2 style="margin-top:0;">{_esc(verb)} {_esc(user.get('username'))}?</h2>
      <p>{detail}</p>
      <form method="post" style="display:flex;gap:.6rem;align-items:center;">
        <button class="btn" type="submit">{_esc(verb)}</button>
        <a href="{url_for('auth.list_users')}">Cancel</a>
      </form>
    </div>"""
    return _shell(verb, body)


@auth_bp.route("/users/deactivate/<id>", methods=["GET", "POST"])
def deactivate_user(id):
    """
    GET confirms, POST deactivates. **There is no delete route, deliberately.**

    `db.py` has no foreign keys, and `created_by` on a user record — and on
    every record the approvals work (B6) will stamp — would dangle the moment a
    row disappeared. A deactivated user cannot log in, which is the whole of
    what removing access means; the name on last year's bill stays readable.
    """
    user = users().get(id)
    if not user:
        return redirect(url_for("auth.list_users", msg="No such user.", type="error"))

    # An Admin who could switch Owners off one at a time would end at an
    # install with exactly one Owner left — and `/users/edit` would then hand
    # them its password. Same guard, same reason.
    refused = _administer_refusal(user)
    if refused:
        return refused

    refusal = _would_strand_install(id, deactivating=True)
    if request.method == "POST":
        if refusal:
            return redirect(url_for("auth.list_users", msg=refusal, type="error"))
        user["active"] = False
        return redirect(url_for("auth.list_users",
                                msg=f"{user['username']} can no longer sign in.",
                                type="success"))

    if refusal:
        return _shell("Cannot deactivate", f"""
        <div class="card" style="max-width:560px;margin:1.5rem auto;">
          <h2 style="margin-top:0;">Cannot deactivate {_esc(user.get('username'))}</h2>
          <p>{_esc(refusal)}</p>
          <p style="margin-bottom:0;">
            <a class="btn" href="{url_for('auth.list_users')}">Back to users</a></p>
        </div>""")

    return _state_change_page(
        user, "Deactivate",
        "They will not be able to sign in. Nothing they created is removed, and "
        "every record still shows their name. This can be undone.",
        url_for("auth.deactivate_user", id=id))


@auth_bp.route("/users/activate/<id>", methods=["GET", "POST"])
def activate_user(id):
    user = users().get(id)
    if not user:
        return redirect(url_for("auth.list_users", msg="No such user.", type="error"))

    # Reactivation is the other half of deactivation and needs the same guard:
    # a dormant Owner account is a live Owner account with one POST, and
    # whoever it belonged to may still know its password.
    refused = _administer_refusal(user)
    if refused:
        return refused

    if request.method == "POST":
        user["active"] = True
        return redirect(url_for("auth.list_users",
                                msg=f"{user['username']} can sign in again.",
                                type="success"))
    return _state_change_page(
        user, "Reactivate", "They will be able to sign in again with their "
        "existing password and roles.", url_for("auth.activate_user", id=id))


# =============================================================================
# ROUTES — roles  (Owner only: these are what a role MEANS)
# =============================================================================

@auth_bp.route("/roles")
def list_roles():
    rows = []
    for r in sorted(roles().values(), key=lambda x: x["name"]):
        holders = sum(1 for u in users().values()
                      if r["id"] in (u.get("role_ids") or []) and u.get("active"))
        tag = '<span class="au-tag owner">Owner tier</span>' if OWNER_PERM in (
            r.get("permissions") or []) else ""
        builtin = '<span class="au-tag">builtin</span>' if r.get("builtin") else ""
        rows.append(f"""
        <tr>
          <td><b>{_esc(r['name'])}</b> {tag} {builtin}</td>
          <td>{len(r.get('permissions') or [])}</td>
          <td>{holders}</td>
          <td><a href="{url_for('auth.edit_role', id=r['id'])}">Edit permissions</a></td>
        </tr>""")

    body = f"""
    {_alert()}
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  flex-wrap:wrap;gap:.75rem;">
        <h2 style="margin:0;">Roles</h2>
        <div style="display:flex;gap:.5rem;">
          <a class="btn" href="{url_for('auth.create_role')}">+ New role</a>
          <a class="btn" href="{url_for('auth.list_users')}">Users</a>
        </div>
      </div>
      <p style="font-size:.85rem;color:#6b7280;margin:.6rem 0 0;">
        A role is a bundle of permissions. A user may hold several; what they
        can do is the union. Editing a role takes effect on the next click, not
        the next sign-in.
      </p>
      <table class="auth-table">
        <thead><tr><th>Role</th><th>Permissions</th><th>Active holders</th><th></th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""
    return _shell("Roles", body)


def _permission_checkboxes(selected) -> str:
    picked = set(selected or [])
    blocks = []
    for group, perms in _permission_groups():
        boxes = []
        for pid, label in perms:
            mark = " checked" if pid in picked else ""
            boxes.append(f'<label><input type="checkbox" name="permissions" '
                         f'value="{_esc(pid)}"{mark}/>'
                         f'<span>{_esc(label)}<br/><code>{_esc(pid)}</code></span></label>')
        blocks.append(f'<div class="perm-group"><h4>{_esc(group)}</h4>'
                      f'<div class="perm-grid">{"".join(boxes)}</div></div>')
    return "".join(blocks)


def _posted_permissions() -> list:
    """
    Only ids that are real permissions (B2).

    The client bundles permissions; the client does not mint them. Anything
    posted that is not a key of `PERMISSIONS` is dropped rather than stored —
    a stored typo grants nothing and is invisible on the page that stored it.
    """
    return sorted(p for p in request.form.getlist("permissions") if p in PERMISSIONS)


@auth_bp.route("/roles/create", methods=["GET", "POST"])
def create_role():
    error = ""
    name = ""
    perms = []
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        perms = _posted_permissions()
        if not name:
            error = "A role name is required."
        elif any((r.get("name") or "").lower() == name.lower() for r in roles().values()):
            error = f"A role called {name!r} already exists."
        else:
            rid = uuid.uuid4().hex[:12]
            roles()[rid] = {"id": rid, "name": name,
                            "permissions": perms, "builtin": False}
            return redirect(url_for("auth.list_roles",
                                    msg=f"Role {name} created.", type="success"))

    err = f'<div class="alert alert-error">{_esc(error)}</div>' if error else ""
    body = f"""
    {err}
    <div class="card">
      <h2 style="margin-top:0;">New role</h2>
      <form method="post" class="auth-form">
        <label class="fld" for="n">Role name</label>
        <input id="n" name="name" type="text" required value="{_esc(name)}"/>
        <p style="margin:1.2rem 0 .6rem;font-weight:600;">Permissions</p>
        {_permission_checkboxes(perms)}
        <p><button class="btn" type="submit">Create role</button>
           <a href="{url_for('auth.list_roles')}" style="margin-left:.6rem;">Cancel</a></p>
      </form>
    </div>"""
    return _shell("New role", body)


@auth_bp.route("/roles/edit/<id>", methods=["GET", "POST"])
def edit_role(id):
    role = roles().get(id)
    if not role:
        return redirect(url_for("auth.list_roles", msg="No such role.", type="error"))

    error = ""
    perms = role.get("permissions") or []
    if request.method == "POST":
        perms = _posted_permissions()
        error = _role_edit_refusal(role, perms)
        if not error:
            role["permissions"] = perms
            if not role.get("builtin"):
                role["name"] = (request.form.get("name") or role["name"]).strip()
            return redirect(url_for("auth.list_roles",
                                    msg=f"{role['name']} updated.", type="success"))

    err = f'<div class="alert alert-error">{_esc(error)}</div>' if error else ""
    name_field = (f'<p><b>{_esc(role["name"])}</b> &mdash; a builtin role; its name is fixed.</p>'
                  if role.get("builtin") else
                  f'<label class="fld" for="n">Role name</label>'
                  f'<input id="n" name="name" type="text" value="{_esc(role["name"])}"/>')
    body = f"""
    {err}
    <div class="card">
      <h2 style="margin-top:0;">Edit {_esc(role['name'])}</h2>
      <form method="post" class="auth-form">
        {name_field}
        <p style="margin:1.2rem 0 .6rem;font-weight:600;">Permissions</p>
        {_permission_checkboxes(perms)}
        <p><button class="btn" type="submit">Save</button>
           <a href="{url_for('auth.list_roles')}" style="margin-left:.6rem;">Cancel</a></p>
      </form>
    </div>"""
    return _shell("Edit role", body)


def _access_log_link() -> str:
    """
    The refusal log's only link in the whole application.

    ⚠ It had **none** until 29 August 2026: `/access-log` was classified,
    permissioned and rendered, and nothing anywhere pointed at it — reachable
    only by typing the URL. It is here rather than on the dashboard's module
    strip deliberately. That strip is a launcher for registers somebody works
    in; this is a **diagnostic**, not an audit trail (ABOUT.md §7 gap 23: an
    in-memory `deque(maxlen=500)` that dies with the process), and putting it
    on the landing page would advertise it as more than it is. `/users` is its
    parent — you come here when somebody says they were refused something.

    Drawn only for a holder of `admin.access_log`, through `can_reach()` rather
    than by naming the permission a second time. An Admin holding `admin.users`
    without it sees the two buttons beside it and not this one, and the route
    still refuses them by URL.
    """
    if not can_reach("auth.access_log"):
        return ""
    return (f'<a class="btn btn-ghost" href="{url_for("auth.access_log")}">'
            f'Refused access</a>')


# =============================================================================
# ROUTES — the refusal log
# =============================================================================

@auth_bp.route("/access-log")
def access_log():
    """
    What the gate refused, and why.

    This is the half of B5's audit mode that survives enforcement: the
    enumeration test proves no endpoint is *unclassified*, but only this shows a
    permission scoped too tight — a real user blocked doing their job. If
    somebody says "it says I cannot", this page names the permission to add.
    """
    rows = "".join(f"""
        <tr>
          <td>{_esc(e['at'])}</td>
          <td>{_esc(e['user'])}</td>
          <td>{_esc(e['method'])} {_esc(e['path'])}<br/>
              <span style="color:#8b93a1;">{_esc(e['endpoint'])}</span></td>
          <td>{_esc(e['permission'])}</td>
          <td>{_esc(e['reason'])}</td>
        </tr>""" for e in REFUSAL_LOG)
    empty = ('<tr><td colspan="5" style="padding:1.5rem;text-align:center;color:#6b7280;">'
             'Nothing has been refused since the last restart.</td></tr>')

    body = f"""
    <div class="card">
      <h2 style="margin-top:0;">Refused access</h2>
      <p style="font-size:.85rem;color:#6b7280;">
        The last {REFUSAL_LOG.maxlen} refusals, newest first. Held in memory and
        cleared by a restart &mdash; this is a diagnostic, not an audit trail.
        The same lines are written to the server log, which does survive.
      </p>
      <table class="auth-table log-tbl">
        <thead><tr><th>When</th><th>User</th><th>Request</th>
                   <th>Permission wanted</th><th>Why</th></tr></thead>
        <tbody>{rows or empty}</tbody>
      </table>
    </div>"""
    return _shell("Refused access", body)
