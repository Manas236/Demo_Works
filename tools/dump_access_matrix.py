"""
tools/dump_access_matrix.py — write docs/ACCESS_MATRIX.md from the live catalogue.

    python tools/dump_access_matrix.py            # writes docs/ACCESS_MATRIX.md
    python tools/dump_access_matrix.py --stdout   # print it instead
    python tools/dump_access_matrix.py --check    # fail if the file is stale

**The output is generated, never hand-edited.** It is read off
`auth.PERMISSIONS`, `auth.ROUTE_PERMISSIONS` and `auth.BUILTIN_ROLES` at run
time, so it can be regenerated after any role edit and it cannot drift from the
code the way a hand-written table would. If the file and the code disagree, the
code is right — INTRODUCTION.md §5.6 — and this script is how you make the file
agree again.

⚠ It reads the **builtin** role definitions in `auth.BUILTIN_ROLES`, not
whatever an Owner has since saved into `STORE["roles"]` on a live install. That
is deliberate: this document is the shipped starting position, which is what
there is to walk the client through. A live install's actual grid is on
`/roles` and is the Owner's to change.

────────────────────────────────────────────────────────────────────────────
WHY EVERY CELL IS MARKED
────────────────────────────────────────────────────────────────────────────
CLIENT_CHANGES-2.md **contains no per-role permission grid.** B4 names six
roles and states exactly one restriction; B3 describes the Owner/Admin split in
five lines. Everything else in a 7 x 61 grid — 427 cells — was decided here, by
us, as a starting position.

That is recorded in the 26 August 2026 override block in CLIENT_CHANGES.md §0
in words: *"The permission set each of the seven roles ships with is therefore a
derived starting position, not a client instruction... It should be walked
through with the client rather than presented as what he asked for."*

A document that does not distinguish the two would let somebody present our
guesses to the client as his own decisions. So every assignment carries a mark:

    §  traceable to a specific line of CLIENT_CHANGES-2.md B2/B3/B4
    ·  our derivation — a starting position, editable, NOT a client instruction

The `SPEC_BACKED` table below is the complete list of what the specification
actually settles. It is short on purpose. If you find yourself wanting to add a
row to it, check the quoted text first — the temptation is to promote a
reasonable inference to a requirement, and that is the exact failure this
marking exists to prevent.
"""

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import auth  # noqa: E402

OUT_PATH = REPO / "docs" / "ACCESS_MATRIX.md"

MARK_SPEC = "§"
MARK_DERIVED = "·"
MARK_ABSENT = ""


# ── What CLIENT_CHANGES-2.md actually settles ──────────────────────────────
#
# Keyed (role slug, permission id) -> the quoted line it comes from. Anything
# not in here is our derivation, and is marked as such.
#
# Read the quotes rather than the keys: each one is the whole of what the
# specification says on the point, and none of them is longer than a sentence.

_B3_OWNER = ('CLIENT_CHANGES-2.md B3 — the Owner tier "Defines what a role '
             '*means*."')
_B3_ADMIN = ('CLIENT_CHANGES-2.md B3 — the Admin tier may "Create users, '
             'deactivate users, assign existing roles."')
_B3_NOT_ROLES = ('CLIENT_CHANGES-2.md B3 — the Admin tier "Cannot alter role '
                 'definitions."')
_B4_HR_WALL = ('CLIENT_CHANGES-2.md B4 — "HR information is restricted from '
               'Sales, Purchase and Accounts."')

SPEC_BACKED = {
    # The Owner tier. B3 gives it everything, and `admin.roles` is the
    # permission that Owner IS — auth.py models the tier as "holds admin.roles"
    # rather than as a flag, so these two cells are the tier itself.
    ("owner", "admin.roles"): _B3_OWNER,
    ("owner", "admin.users"): _B3_OWNER,

    # The Admin tier. B3 names Yogesh / a Director, and gives it user
    # administration and explicitly NOT role definition. `admin.users` present
    # and `admin.roles` absent are the two cells that make the split real.
    ("director", "admin.users"): _B3_ADMIN,
    ("director", "admin.roles"): _B3_NOT_ROLES,          # asserted ABSENT

    # B4's one stated restriction. `charge.py` is the wages and site-expense
    # ledger and is the only surface in the app today that "HR information"
    # can attach to, so the wall is drawn there. All four charge permissions
    # are withheld from all three roles: twelve cells, each asserted ABSENT.
}
for _role in ("sales-manager", "purchase-manager", "accountant"):
    for _perm in ("charge.view", "charge.create", "charge.edit", "charge.delete"):
        SPEC_BACKED[(_role, _perm)] = _B4_HR_WALL

# Cells the specification requires to be EMPTY rather than filled. Marked in
# the grid so a reader can see the restriction was applied rather than merely
# not thought about — an empty cell and a deliberately empty cell look
# identical otherwise, which is how a stated restriction gets quietly dropped.
SPEC_REQUIRES_ABSENT = {
    ("director", "admin.roles"),
}
for _role in ("sales-manager", "purchase-manager", "accountant"):
    for _perm in ("charge.view", "charge.create", "charge.edit", "charge.delete"):
        SPEC_REQUIRES_ABSENT.add((_role, _perm))


# ── Plain-English role descriptions ────────────────────────────────────────
#
# The one part of this document that is prose rather than a generated table.
# Each is checked against the live permission set at generation time: if a role
# gains or loses a permission that a sentence here claims, `--check` fails and
# the sentence has to be rewritten. A description that drifts from the grid
# above it is worse than none, because the grid is the part nobody reads.

ROLE_NOTES = {
    "owner": {
        "can": "Everything, including the one thing nobody else can do: change "
               "what a role means. An Owner ticks and unticks the boxes that "
               "define Director, HR, Sales Manager and the rest, which is "
               "effectively the power to grant themselves or anybody else any "
               "permission in the system.",
        "cannot": "Nothing is withheld. There is one thing an Owner is stopped "
                  "from doing to themselves: if they are the last active Owner, "
                  "they cannot deactivate their own account or edit the Owner "
                  "role off it, because that would leave an installation nobody "
                  "can administer and there is no password-reset e-mail to "
                  "recover from it.",
        "claims": {"holds": ["admin.roles", "admin.users", "settings.edit"]},
    },
    "director": {
        "can": "Everything operational, plus the whole of user administration: "
               "create staff accounts, deactivate someone who has left, assign "
               "any existing role, and read the refused-access log. They can "
               "also edit the company identity and bank details at Settings.",
        "cannot": "**Change what a role means.** This is the single line "
                  "between Director and Owner, and it is the point of the "
                  "split: a Director who could edit role definitions could give "
                  "themselves any permission in the system, so \"cannot alter "
                  "role definitions\" would mean nothing. They also cannot "
                  "grant anybody the Owner role, or create a new Owner account "
                  "— that would be the same escalation by another door.",
        "claims": {"holds": ["admin.users", "settings.edit", "charge.view"],
                   "lacks": ["admin.roles"]},
    },
    "operation-head": {
        "can": "Run the work. Write and revise schedules, raise and issue RA "
               "bills, cancel them, print everything, raise delivery challans "
               "and draft purchase orders, convert those into real purchase "
               "orders, and record wages and site expenses against a project.",
        "cannot": "Touch the sell chain — no quotations, proforma invoices or "
                  "tax invoices. Record or edit money received. Administer "
                  "users or roles. Delete a charge once it is recorded, or "
                  "change the company identity.",
        "claims": {"holds": ["boq.create", "ra.issue", "dc.create", "charge.create"],
                   "lacks": ["quotation.create", "invoice.create", "receipt.create",
                             "admin.users", "charge.delete", "settings.edit"]},
    },
    "hr": {
        "can": "The wages and site-expense ledger, and the address book. Record "
               "a charge, edit it, and delete one.",
        "cannot": "Everything else. HR sees no schedule, no bill, no quotation, "
                  "no purchase order and no money received. This is the "
                  "narrowest role in the system and deliberately so — but read "
                  "the warning below the grid: **the employee master HR "
                  "actually needs does not exist yet**, so what this role can "
                  "reach today is a stand-in, not the job.",
        "claims": {"holds": ["charge.view", "charge.delete", "address.view"],
                   "lacks": ["boq.view", "ra.view", "quotation.view",
                             "purchase.view", "receipt.view", "admin.users"]},
    },
    "sales-manager": {
        "can": "The whole sell chain: write quotations, raise proforma "
               "invoices, raise tax invoices, and keep the client register and "
               "the address book up to date. They can also write and print "
               "schedules, and read and print RA bills.",
        "cannot": "**See the wages ledger** — this is B4's one stated "
                  "restriction, applied literally. They cannot raise or issue "
                  "an RA bill (reading and printing only), record money "
                  "received, touch the buy side at all, or administer users.",
        "claims": {"holds": ["quotation.create", "invoice.create", "client.edit",
                             "boq.create", "ra.print"],
                   "lacks": ["charge.view", "ra.create", "ra.issue",
                             "receipt.create", "purchase.view", "admin.users"]},
    },
    "purchase-manager": {
        "can": "The whole buy side: raise purchase orders and update their "
               "status, write and price draft POs, and raise and print delivery "
               "challans. They can read schedules, the catalogue and the "
               "specification library, and keep the address book current.",
        "cannot": "**See the wages ledger** — B4's stated restriction again. "
                  "They cannot touch the sell chain, RA bills or money "
                  "received, delete a delivery challan once raised, or "
                  "administer users.",
        "claims": {"holds": ["purchase.create", "po.create", "dc.create",
                             "address.edit"],
                   "lacks": ["charge.view", "quotation.view", "ra.view",
                             "receipt.view", "admin.users"]},
    },
    "accountant": {
        "can": "Money in. Record, edit and delete receipts against RA bills, "
               "and read the client register. They can read — and print — RA "
               "bills, and read tax invoices, proforma invoices, purchase "
               "orders, schedules and projects.",
        "cannot": "**See the wages ledger** — B4's stated restriction, and the "
                  "one most likely to be questioned, because an accountant "
                  "booking wages is ordinary. It is withheld because the "
                  "specification says Accounts is on the far side of the HR "
                  "wall; if the client wants it, it is a checkbox and not a "
                  "deployment. They also cannot create or edit any document — "
                  "no quotation, no invoice, no bill, no purchase order — and "
                  "cannot administer users.",
        "claims": {"holds": ["receipt.create", "receipt.delete", "client.view",
                             "ra.print", "invoice.view"],
                   "lacks": ["charge.view", "invoice.create", "ra.create",
                             "quotation.create", "purchase.create", "admin.users"]},
    },
}


# ── Building the document ──────────────────────────────────────────────────

def _role_permissions() -> dict:
    """slug -> (display name, set of permission ids), from BUILTIN_ROLES."""
    return {slug: (name, set(perms))
            for slug, (name, perms) in auth.BUILTIN_ROLES.items()}


def _verify_prose(roles: dict) -> list:
    """
    Every 'holds'/'lacks' claim in ROLE_NOTES, checked against the live grid.

    The prose is the half of this document a person actually reads, so a
    sentence that has drifted from the table above it is the worst failure this
    file can have. Every claim is checkable and every claim is checked.
    """
    problems = []
    for slug, note in ROLE_NOTES.items():
        if slug not in roles:
            problems.append(f"ROLE_NOTES describes {slug!r}, which is not a role")
            continue
        _name, held = roles[slug]
        for perm in note.get("claims", {}).get("holds", []):
            if perm not in held:
                problems.append(
                    f"{slug}: the description says it can do {perm!r}, and it "
                    f"does not hold that permission")
        for perm in note.get("claims", {}).get("lacks", []):
            if perm in held:
                problems.append(
                    f"{slug}: the description says it cannot do {perm!r}, and "
                    f"it holds that permission")
    for slug in roles:
        if slug not in ROLE_NOTES:
            problems.append(f"role {slug!r} has no plain-English description")
    return problems


def _endpoints_for(permission: str) -> list:
    return sorted(e for e, p in auth.ROUTE_PERMISSIONS.items() if p == permission)


def build() -> str:
    roles = _role_permissions()
    slugs = ["owner", "director", "operation-head", "hr",
             "sales-manager", "purchase-manager", "accountant"]
    slugs += [s for s in roles if s not in slugs]

    problems = _verify_prose(roles)
    if problems:
        raise SystemExit(
            "the plain-English role descriptions disagree with the live "
            "permission grid:\n  " + "\n  ".join(problems) +
            "\n\nFix the prose in tools/dump_access_matrix.py (or the role "
            "definition in auth.py), then regenerate.")

    spec_cells = sum(1 for key in SPEC_BACKED if key[0] in roles)
    total_cells = len(slugs) * len(auth.PERMISSIONS)

    out = []
    w = out.append

    w("# Access matrix — who can do what")
    w("")
    w("> **Generated file. Do not edit it by hand.**")
    w("> Written by [`tools/dump_access_matrix.py`](../tools/dump_access_matrix.py)")
    w("> from `auth.PERMISSIONS`, `auth.ROUTE_PERMISSIONS` and")
    w("> `auth.BUILTIN_ROLES`. Regenerate it after any change to a role:")
    w("> `python tools/dump_access_matrix.py`.")
    w("")
    w(f"**{len(slugs)} roles · {len(auth.PERMISSIONS)} permissions · "
      f"{len(auth.ROUTE_PERMISSIONS)} classified endpoints.**")
    w("")
    w("---")
    w("")

    # ── The warning that has to come before the table ──────────────────────
    w("## ⚠ Read this before you show anyone the grid")
    w("")
    w("**CLIENT_CHANGES-2.md contains no per-role permission grid.** B4 names "
      "six roles and states exactly one restriction. B3 describes the "
      "Owner/Admin split in five lines. That is the whole of the "
      "specification on this subject.")
    w("")
    w(f"This grid has **{total_cells} cells**. **{spec_cells}** of them can be "
      f"traced to a line of the specification. The rest — "
      f"**{total_cells - spec_cells}** — are a **starting position we chose**, "
      f"and they are marked so that nobody presents them to the client as "
      f"something he asked for.")
    w("")
    w("| mark | meaning |")
    w("|---|---|")
    w(f"| `{MARK_SPEC}` | **Specification.** Traceable to a quoted line of "
      f"CLIENT_CHANGES-2.md B2/B3/B4. Listed in full below the grid. |")
    w(f"| `{MARK_DERIVED}` | **Our derivation.** A reasonable starting position, "
      f"not a client instruction. Editable with a checkbox on `/roles`. |")
    w("| *(blank)* | The role does not hold this permission. |")
    w(f"| `{MARK_SPEC}` *on a blank cell* | The specification requires this to "
      f"be **withheld**. Shown so a deliberate exclusion is not mistaken for "
      f"an oversight. |")
    w("")
    w("Every derived cell is a question for the client, and none of them is "
      "expensive to change: an Owner reassigns any of it with checkboxes at "
      "`/roles`, with no deployment and no developer.")
    w("")
    w("---")
    w("")

    # ── The grid ───────────────────────────────────────────────────────────
    w("## 1. The grid")
    w("")
    w("Grouped the way the role editor groups them, so this page and that "
      "screen can be read side by side.")
    w("")

    header = "| Permission | " + " | ".join(roles[s][0] for s in slugs) + " |"
    divider = "|---|" + "|".join([":-:"] * len(slugs)) + "|"

    for group, perms in auth._permission_groups():
        w(f"### {group}")
        w("")
        w(header)
        w(divider)
        for pid, label in perms:
            cells = []
            for slug in slugs:
                held = pid in roles[slug][1]
                key = (slug, pid)
                if held:
                    cells.append(MARK_SPEC if key in SPEC_BACKED else MARK_DERIVED)
                elif key in SPEC_REQUIRES_ABSENT:
                    cells.append(MARK_SPEC)
                else:
                    cells.append(MARK_ABSENT)
            w(f"| {label}<br/>`{pid}` | " + " | ".join(cells) + " |")
        w("")

    totals = "| **Total permissions held** | " + " | ".join(
        f"**{len(roles[s][1])}**" for s in slugs) + " |"
    w("### Totals")
    w("")
    w(header)
    w(divider)
    w(totals)
    w("")
    w("---")
    w("")

    # ── What the specification actually settles ────────────────────────────
    w("## 2. The cells the specification settles")
    w("")
    w("Every cell marked `§` above, with the line it comes from. This list is "
      "short, and its shortness is the point.")
    w("")
    seen = {}
    for (slug, pid), quote in sorted(SPEC_BACKED.items()):
        if slug not in roles:
            continue
        seen.setdefault(quote, []).append((roles[slug][0], pid,
                                           pid in roles[slug][1]))
    for quote, cells in seen.items():
        w(f"**{quote}**")
        w("")
        for role_name, pid, held in sorted(cells):
            state = "holds" if held else "**does not hold**"
            w(f"- {role_name} {state} `{pid}`")
        w("")
    w("Everything else in the grid is ours.")
    w("")
    w("---")
    w("")

    # ── Plain English ──────────────────────────────────────────────────────
    w("## 3. Each role, in plain English")
    w("")
    w("Written for somebody who has not read the code, and checked against the "
      "grid above every time this file is generated — a claim here that the "
      "permissions do not support fails the generator.")
    w("")
    for slug in slugs:
        name, held = roles[slug]
        note = ROLE_NOTES[slug]
        w(f"### {name}")
        w("")
        w(f"*{len(held)} of {len(auth.PERMISSIONS)} permissions.*")
        w("")
        w(f"**What they can do.** {note['can']}")
        w("")
        w(f"**What they explicitly cannot do.** {note['cannot']}")
        w("")

    w("---")
    w("")

    # ── The caveats that a grid cannot show ────────────────────────────────
    w("## 4. Four things the grid does not show")
    w("")
    w("**1. A user may hold several roles, and gets the union.** "
      "CLIENT_CHANGES-2.md B4: *\"One user may hold several roles — the client "
      "explicitly wants Sales and Purchase linkable.\"* So somebody who is both "
      "Sales Manager and Purchase Manager can do everything in both columns. "
      "Read the grid as *what each role adds*, never as *what a person is "
      "limited to*.")
    w("")
    w("**2. Withholding a permission does not withhold the information.** "
      "The HR wall is drawn at the wages ledger because that is the only "
      "employee data this application holds. A Sales Manager who cannot open "
      "the charges ledger can still read a project page, and B4's restriction "
      "is about pay, not about projects. **The employee master HR actually "
      "needs does not exist yet** (CLIENT_CHANGES-2.md C4, not built), so the "
      "HR role today is a placeholder for a job rather than the job.")
    w("")
    w("**3. Permissions are per page, not per record.** The gate answers *\"may "
      "this user issue RA bills\"*. It cannot answer *\"may this user issue "
      "**this** RA bill\"*. Nothing here restricts anybody to their own "
      "projects, their own clients or their own documents. This is ABOUT.md §7 "
      "gap 24, and it is the load-bearing part of the approvals work (B6): "
      "*\"a user cannot approve a record they created\"* is a per-record "
      "question and cannot be expressed in this grid at all.")
    w("")
    w("**4. A page that accepts both reading and writing is classified once.** "
      "The registry maps an endpoint to one permission, and most pages answer "
      "both GET and POST on one endpoint. Usually that is right and is stricter "
      "than splitting them. One route needed a separate guard for its write "
      "path — `/projects/view/<id>`, where attaching a schedule to a project "
      "is a change made through a page that is otherwise a read. ABOUT.md §7 "
      "gap 24b.")
    w("")
    w("---")
    w("")

    # ── Endpoint appendix ──────────────────────────────────────────────────
    w("## 5. Appendix — which pages each permission opens")
    w("")
    w("Read off the live route registry, so it cannot drift from what the "
      "application actually enforces.")
    w("")
    w("| Permission | Opens |")
    w("|---|---|")
    for group, perms in auth._permission_groups():
        for pid, _label in perms:
            endpoints = _endpoints_for(pid)
            w(f"| `{pid}` | " + (", ".join(f"`{e}`" for e in endpoints) or "—") + " |")
    w("")
    w("Two endpoint classes carry no permission at all:")
    w("")
    public = sorted(e for e, p in auth.ROUTE_PERMISSIONS.items() if p == auth.PUBLIC)
    authed = sorted(e for e, p in auth.ROUTE_PERMISSIONS.items()
                    if p == auth.AUTHENTICATED)
    w(f"- **Reachable with no account at all:** {', '.join(f'`{e}`' for e in public)}. "
      f"`auth.setup` is public only while no user exists and refuses — GET and "
      f"POST both — the moment one does.")
    w(f"- **Any signed-in user, no permission needed:** "
      f"{', '.join(f'`{e}`' for e in authed)}.")
    w("")
    w("**Anything not in the registry is refused to everybody, including an "
      "Owner.** That is the design: a page added later is unreachable until "
      "somebody classifies it, rather than being open until somebody notices.")
    w("")

    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true",
                        help="print the document instead of writing it")
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the file on disk is out of date")
    args = parser.parse_args()

    text = build()

    if args.stdout:
        sys.stdout.write(text)
        return 0

    if args.check:
        if not OUT_PATH.exists():
            print(f"{OUT_PATH} does not exist — run this script without --check")
            return 1
        if OUT_PATH.read_text(encoding="utf8") != text:
            print(f"{OUT_PATH} is out of date. Regenerate it:\n"
                  f"    python tools/dump_access_matrix.py")
            return 1
        print(f"{OUT_PATH} is up to date")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf8")
    print(f"wrote {OUT_PATH}  ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
