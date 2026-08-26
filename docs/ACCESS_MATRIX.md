# Access matrix — who can do what

> **Generated file. Do not edit it by hand.**
> Written by [`tools/dump_access_matrix.py`](../tools/dump_access_matrix.py)
> from `auth.PERMISSIONS`, `auth.ROUTE_PERMISSIONS` and
> `auth.BUILTIN_ROLES`. Regenerate it after any change to a role:
> `python tools/dump_access_matrix.py`.

**7 roles · 61 permissions · 85 classified endpoints.**

---

## ⚠ Read this before you show anyone the grid

**CLIENT_CHANGES-2.md contains no per-role permission grid.** B4 names six roles and states exactly one restriction. B3 describes the Owner/Admin split in five lines. That is the whole of the specification on this subject.

This grid has **427 cells**. **16** of them can be traced to a line of the specification. The rest — **411** — are a **starting position we chose**, and they are marked so that nobody presents them to the client as something he asked for.

| mark | meaning |
|---|---|
| `§` | **Specification.** Traceable to a quoted line of CLIENT_CHANGES-2.md B2/B3/B4. Listed in full below the grid. |
| `·` | **Our derivation.** A reasonable starting position, not a client instruction. Editable with a checkbox on `/roles`. |
| *(blank)* | The role does not hold this permission. |
| `§` *on a blank cell* | The specification requires this to be **withheld**. Shown so a deliberate exclusion is not mistaken for an oversight. |

Every derived cell is a question for the client, and none of them is expensive to change: an Owner reassigns any of it with checkboxes at `/roles`, with no deployment and no developer.

---

## 1. The grid

Grouped the way the role editor groups them, so this page and that screen can be read side by side.

### General

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View the dashboard<br/>`dashboard.view` | · | · | · | · | · | · | · |
| View market news<br/>`extractor.view` | · | · |  |  |  |  |  |

### BOQ chain

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View bills of quantities<br/>`boq.view` | · | · | · |  | · | · | · |
| Create and revise a BOQ<br/>`boq.create` | · | · | · |  | · |  |  |
| Print a BOQ<br/>`boq.print` | · | · | · |  | · |  |  |

### RA billing

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View RA bills<br/>`ra.view` | · | · | · |  | · |  | · |
| Raise an RA bill<br/>`ra.create` | · | · | · |  |  |  |  |
| Edit a draft RA bill<br/>`ra.edit` | · | · | · |  |  |  |  |
| Delete a draft RA bill<br/>`ra.delete` | · | · | · |  |  |  |  |
| Issue an RA bill<br/>`ra.issue` | · | · | · |  |  |  |  |
| Cancel an issued RA bill<br/>`ra.cancel` | · | · | · |  |  |  |  |
| Print an RA bill<br/>`ra.print` | · | · | · |  | · |  | · |

### Money in

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View receipts<br/>`receipt.view` | · | · | · |  |  |  | · |
| Record a receipt<br/>`receipt.create` | · | · |  |  |  |  | · |
| Edit a receipt<br/>`receipt.edit` | · | · |  |  |  |  | · |
| Delete a receipt<br/>`receipt.delete` | · | · |  |  |  |  | · |
| View the client register<br/>`client.view` | · | · | · |  | · |  | · |
| Edit a client's party details<br/>`client.edit` | · | · |  |  | · |  |  |

### Quotation chain

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View quotations<br/>`quotation.view` | · | · |  |  | · |  |  |
| Create a quotation<br/>`quotation.create` | · | · |  |  | · |  |  |
| Update a quotation's deal fields<br/>`quotation.edit` | · | · |  |  | · |  |  |
| View proforma invoices<br/>`proforma.view` | · | · |  |  | · |  | · |
| Raise a proforma invoice<br/>`proforma.create` | · | · |  |  | · |  |  |
| View tax invoices<br/>`invoice.view` | · | · |  |  | · |  | · |
| Raise a tax invoice<br/>`invoice.create` | · | · |  |  | · |  |  |

### Buy side

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View purchase orders<br/>`purchase.view` | · | · | · |  |  | · | · |
| Raise a purchase order<br/>`purchase.create` | · | · | · |  |  | · |  |
| Update a purchase order's status<br/>`purchase.edit` | · | · | · |  |  | · |  |
| View draft purchase orders<br/>`po.view` | · | · | · |  |  | · |  |
| Raise a draft purchase order<br/>`po.create` | · | · | · |  |  | · |  |
| Edit a draft purchase order<br/>`po.edit` | · | · | · |  |  | · |  |
| Delete a draft purchase order<br/>`po.delete` | · | · | · |  |  | · |  |
| Print a draft purchase order<br/>`po.print` | · | · | · |  |  | · |  |

### Dispatch

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View delivery challans<br/>`dc.view` | · | · | · |  |  | · |  |
| Raise a delivery challan<br/>`dc.create` | · | · | · |  |  | · |  |
| Edit a delivery challan<br/>`dc.edit` | · | · | · |  |  | · |  |
| Delete a delivery challan<br/>`dc.delete` | · | · | · |  |  |  |  |
| Print a delivery challan<br/>`dc.print` | · | · | · |  |  | · |  |

### Employee costs

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View employee and misc charges<br/>`charge.view` | · | · | · | · | § | § | § |
| Record a charge<br/>`charge.create` | · | · | · | · | § | § | § |
| Edit a charge<br/>`charge.edit` | · | · | · | · | § | § | § |
| Delete a charge<br/>`charge.delete` | · | · |  | · | § | § | § |

### Projects

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View projects<br/>`project.view` | · | · | · |  | · | · | · |
| Create a project<br/>`project.create` | · | · | · |  |  |  |  |
| Edit a project<br/>`project.edit` | · | · | · |  |  |  |  |
| Delete a project<br/>`project.delete` | · | · |  |  |  |  |  |

### Library

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View the specification library<br/>`spec.view` | · | · | · |  | · | · |  |
| Add a specification<br/>`spec.create` | · | · | · |  |  |  |  |
| Edit a specification<br/>`spec.edit` | · | · | · |  |  |  |  |
| Delete a specification<br/>`spec.delete` | · | · |  |  |  |  |  |
| View the product catalogue<br/>`product.view` | · | · | · |  | · | · |  |
| Add a product<br/>`product.create` | · | · |  |  |  |  |  |
| Delete a product<br/>`product.delete` | · | · |  |  |  |  |  |
| View the address book<br/>`address.view` | · | · | · | · | · | · |  |
| Add an address<br/>`address.create` | · | · | · |  | · | · |  |
| Edit an address<br/>`address.edit` | · | · | · |  | · | · |  |
| Delete an address<br/>`address.delete` | · | · |  |  |  |  |  |

### Administration

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Edit company identity and bank details<br/>`settings.edit` | · | · |  |  |  |  |  |
| Create, edit and deactivate users<br/>`admin.users` | § | § |  |  |  |  |  |
| Define what a role means<br/>`admin.roles` | § | § |  |  |  |  |  |
| Read the refused-access log<br/>`admin.access_log` | · | · |  |  |  |  |  |

### Totals

| Permission | Owner | Director | Operation Head | HR | Sales Manager | Purchase Manager | Accountant |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Total permissions held** | **61** | **60** | **39** | **6** | **21** | **20** | **13** |

---

## 2. The cells the specification settles

Every cell marked `§` above, with the line it comes from. This list is short, and its shortness is the point.

**CLIENT_CHANGES-2.md B4 — "HR information is restricted from Sales, Purchase and Accounts."**

- Accountant **does not hold** `charge.create`
- Accountant **does not hold** `charge.delete`
- Accountant **does not hold** `charge.edit`
- Accountant **does not hold** `charge.view`
- Purchase Manager **does not hold** `charge.create`
- Purchase Manager **does not hold** `charge.delete`
- Purchase Manager **does not hold** `charge.edit`
- Purchase Manager **does not hold** `charge.view`
- Sales Manager **does not hold** `charge.create`
- Sales Manager **does not hold** `charge.delete`
- Sales Manager **does not hold** `charge.edit`
- Sales Manager **does not hold** `charge.view`

**CLIENT_CHANGES-2.md B3 — the Admin tier "Cannot alter role definitions."**

- Director **does not hold** `admin.roles`

**CLIENT_CHANGES-2.md B3 — the Admin tier may "Create users, deactivate users, assign existing roles."**

- Director holds `admin.users`

**CLIENT_CHANGES-2.md B3 — the Owner tier "Defines what a role *means*."**

- Owner holds `admin.roles`
- Owner holds `admin.users`

Everything else in the grid is ours.

---

## 3. Each role, in plain English

Written for somebody who has not read the code, and checked against the grid above every time this file is generated — a claim here that the permissions do not support fails the generator.

### Owner

*61 of 61 permissions.*

**What they can do.** Everything, including the one thing nobody else can do: change what a role means. An Owner ticks and unticks the boxes that define Director, HR, Sales Manager and the rest, which is effectively the power to grant themselves or anybody else any permission in the system.

**What they explicitly cannot do.** Nothing is withheld. There is one thing an Owner is stopped from doing to themselves: if they are the last active Owner, they cannot deactivate their own account or edit the Owner role off it, because that would leave an installation nobody can administer and there is no password-reset e-mail to recover from it.

### Director

*60 of 61 permissions.*

**What they can do.** Everything operational, plus the whole of user administration: create staff accounts, deactivate someone who has left, assign any existing role, and read the refused-access log. They can also edit the company identity and bank details at Settings.

**What they explicitly cannot do.** **Change what a role means.** This is the single line between Director and Owner, and it is the point of the split: a Director who could edit role definitions could give themselves any permission in the system, so "cannot alter role definitions" would mean nothing. They also cannot grant anybody the Owner role, or create a new Owner account — that would be the same escalation by another door.

### Operation Head

*39 of 61 permissions.*

**What they can do.** Run the work. Write and revise schedules, raise and issue RA bills, cancel them, print everything, raise delivery challans and draft purchase orders, convert those into real purchase orders, and record wages and site expenses against a project.

**What they explicitly cannot do.** Touch the sell chain — no quotations, proforma invoices or tax invoices. Record or edit money received. Administer users or roles. Delete a charge once it is recorded, or change the company identity.

### HR

*6 of 61 permissions.*

**What they can do.** The wages and site-expense ledger, and the address book. Record a charge, edit it, and delete one.

**What they explicitly cannot do.** Everything else. HR sees no schedule, no bill, no quotation, no purchase order and no money received. This is the narrowest role in the system and deliberately so — but read the warning below the grid: **the employee master HR actually needs does not exist yet**, so what this role can reach today is a stand-in, not the job.

### Sales Manager

*21 of 61 permissions.*

**What they can do.** The whole sell chain: write quotations, raise proforma invoices, raise tax invoices, and keep the client register and the address book up to date. They can also write and print schedules, and read and print RA bills.

**What they explicitly cannot do.** **See the wages ledger** — this is B4's one stated restriction, applied literally. They cannot raise or issue an RA bill (reading and printing only), record money received, touch the buy side at all, or administer users.

### Purchase Manager

*20 of 61 permissions.*

**What they can do.** The whole buy side: raise purchase orders and update their status, write and price draft POs, and raise and print delivery challans. They can read schedules, the catalogue and the specification library, and keep the address book current.

**What they explicitly cannot do.** **See the wages ledger** — B4's stated restriction again. They cannot touch the sell chain, RA bills or money received, delete a delivery challan once raised, or administer users.

### Accountant

*13 of 61 permissions.*

**What they can do.** Money in. Record, edit and delete receipts against RA bills, and read the client register. They can read — and print — RA bills, and read tax invoices, proforma invoices, purchase orders, schedules and projects.

**What they explicitly cannot do.** **See the wages ledger** — B4's stated restriction, and the one most likely to be questioned, because an accountant booking wages is ordinary. It is withheld because the specification says Accounts is on the far side of the HR wall; if the client wants it, it is a checkbox and not a deployment. They also cannot create or edit any document — no quotation, no invoice, no bill, no purchase order — and cannot administer users.

---

## 4. Four things the grid does not show

**1. A user may hold several roles, and gets the union.** CLIENT_CHANGES-2.md B4: *"One user may hold several roles — the client explicitly wants Sales and Purchase linkable."* So somebody who is both Sales Manager and Purchase Manager can do everything in both columns. Read the grid as *what each role adds*, never as *what a person is limited to*.

**2. Withholding a permission does not withhold the information.** The HR wall is drawn at the wages ledger because that is the only employee data this application holds. A Sales Manager who cannot open the charges ledger can still read a project page, and B4's restriction is about pay, not about projects. **The employee master HR actually needs does not exist yet** (CLIENT_CHANGES-2.md C4, not built), so the HR role today is a placeholder for a job rather than the job.

**3. Permissions are per page, not per record.** The gate answers *"may this user issue RA bills"*. It cannot answer *"may this user issue **this** RA bill"*. Nothing here restricts anybody to their own projects, their own clients or their own documents. This is ABOUT.md §7 gap 24, and it is the load-bearing part of the approvals work (B6): *"a user cannot approve a record they created"* is a per-record question and cannot be expressed in this grid at all.

**4. A page that accepts both reading and writing is classified once.** The registry maps an endpoint to one permission, and most pages answer both GET and POST on one endpoint. Usually that is right and is stricter than splitting them. One route needed a separate guard for its write path — `/projects/view/<id>`, where attaching a schedule to a project is a change made through a page that is otherwise a read. ABOUT.md §7 gap 24b.

---

## 5. Appendix — which pages each permission opens

Read off the live route registry, so it cannot drift from what the application actually enforces.

| Permission | Opens |
|---|---|
| `dashboard.view` | `dashboard.index` |
| `extractor.view` | `extractor.index` |
| `boq.view` | `boq.list_boqs`, `boq.view_boq` |
| `boq.create` | `boq.create_boq` |
| `boq.print` | `boq.print_boq` |
| `ra.view` | `ra.list_ras`, `ra.view_ra` |
| `ra.create` | `ra.create_ra` |
| `ra.edit` | `ra.edit_ra` |
| `ra.delete` | `ra.delete_ra` |
| `ra.issue` | `ra.issue_ra` |
| `ra.cancel` | `ra.cancel_ra` |
| `ra.print` | `ra.print_ra` |
| `receipt.view` | `receipt.list_receipts` |
| `receipt.create` | `receipt.new_receipt` |
| `receipt.edit` | `receipt.edit_receipt` |
| `receipt.delete` | `receipt.delete_receipt` |
| `client.view` | `client.list_clients` |
| `client.edit` | `client.edit_party` |
| `quotation.view` | `quotation.list_quotations`, `quotation.view_quotation` |
| `quotation.create` | `quotation.create_quotation` |
| `quotation.edit` | `quotation.update_quotation` |
| `proforma.view` | `proforma.list_proformas`, `proforma.view_proforma` |
| `proforma.create` | `proforma.create_proforma` |
| `invoice.view` | `invoice.list_invoices`, `invoice.view_invoice` |
| `invoice.create` | `invoice.create_invoice` |
| `purchase.view` | `purchase.list_purchases`, `purchase.view_purchase` |
| `purchase.create` | `purchase.create_purchase`, `purchase.from_boq`, `purchase.from_draft` |
| `purchase.edit` | `purchase.update_purchase` |
| `po.view` | `po_draft.list_pos`, `po_draft.view_po` |
| `po.create` | `po_draft.create_po` |
| `po.edit` | `po_draft.edit_po` |
| `po.delete` | `po_draft.delete_po` |
| `po.print` | `po_draft.print_po` |
| `dc.view` | `challan.list_dcs`, `challan.view_dc` |
| `dc.create` | `challan.create_dc` |
| `dc.edit` | `challan.edit_dc` |
| `dc.delete` | `challan.delete_dc` |
| `dc.print` | `challan.print_dc` |
| `charge.view` | `charge.list_charges` |
| `charge.create` | `charge.new_charge` |
| `charge.edit` | `charge.edit_charge` |
| `charge.delete` | `charge.delete_charge` |
| `project.view` | `project.list_projects`, `projectview.view_project` |
| `project.create` | `project.create_project` |
| `project.edit` | `project.edit_project` |
| `project.delete` | `project.delete_project` |
| `spec.view` | `spec.list_specs`, `spec.view_spec` |
| `spec.create` | `spec.add_spec` |
| `spec.edit` | `spec.edit_spec` |
| `spec.delete` | `spec.delete_spec` |
| `product.view` | `product.list_products`, `product.view_product` |
| `product.create` | `product.add_product` |
| `product.delete` | `product.delete_product` |
| `address.view` | `address.list_addresses` |
| `address.create` | `address.add_address` |
| `address.edit` | `address.edit_address` |
| `address.delete` | `address.delete_address` |
| `settings.edit` | `settings.edit_settings` |
| `admin.users` | `auth.activate_user`, `auth.create_user`, `auth.deactivate_user`, `auth.edit_user`, `auth.list_users` |
| `admin.roles` | `auth.create_role`, `auth.edit_role`, `auth.list_roles` |
| `admin.access_log` | `auth.access_log` |

Two endpoint classes carry no permission at all:

- **Reachable with no account at all:** `auth.login`, `auth.setup`, `static`. `auth.setup` is public only while no user exists and refuses — GET and POST both — the moment one does.
- **Any signed-in user, no permission needed:** `auth.account`, `auth.logout`.

**Anything not in the registry is refused to everybody, including an Owner.** That is the design: a page added later is unreachable until somebody classifies it, rather than being open until somebody notices.

