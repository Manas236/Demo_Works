"""
The import graph, enforced.

ABOUT.md §2 documents which module may import which, and every one of those
arrows is load-bearing: reversing one is a circular import that fails at boot,
and the app's whole no-templates architecture depends on `dashboard.py` sitting
at the bottom of the graph where every other module can pull `BASE_STYLES` out
of it.

ABOUT.md claimed "there is a test guarding every one of those six import
directions". There was not — this file is that guard, written when the BOQ
chain was added and covering the original six as well as the new ones.

The check is on the module's own source, not on `sys.modules`: importing
`quotation` pulls `proforma` into the process by way of nothing at all, but a
transitive import through another module would still make a naive
`sys.modules` check pass. Reading the AST asks the only question that matters —
does THIS file contain an import of that module.
"""

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def imports_of(module: str, top_level_only: bool = False) -> set:
    """
    Every module name imported by `module`, from its source.

    `top_level_only` restricts the answer to imports that run at import time.
    That distinction is the whole point for `dashboard.py`: it may not import
    `product` or `address` at module level, because both import *it* — but
    `index()` pulls the seeders in **inside the function body**, which breaks
    the cycle and is deliberate (ABOUT.md §2). A check that could not tell the
    two apart would report the documented design as a violation.
    """
    tree = ast.parse((REPO / f"{module}.py").read_text(encoding="utf8"))
    nodes = tree.body if top_level_only else ast.walk(tree)
    found = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


# ── The directions ABOUT.md §2 already documented ───────────────────────────
# `scope` is "any" when the module may not import the other at all, and
# "module" when a deliberate in-function import is the documented escape hatch.
FORBIDDEN = [
    # (module, must-not-import, scope, why)
    ("pipeline",  "quotation", "any", "pipeline.py imports nothing from the app — it is the "
                                      "only place a helper can live without coupling the two pipelines"),
    ("dashboard", "quotation", "any", "dashboard.py is imported BY every module; importing one back is a cycle"),
    ("dashboard", "product",   "module", "index() imports the seeders inside the function body — "
                                         "at module level it would be a cycle"),
    ("dashboard", "address",   "module", "same reason"),
    ("quotation", "proforma",  "any", "the chain imports strictly downstream; quotation links out with url_for"),

    # ⚠ **`quotation` -> `purchase` is scope "module", not "any", from
    #   29 August 2026.** The deal panel calls `purchase.job_cost()` rather than
    #   re-deriving a second `committed` beside it, and it takes the import
    #   INSIDE `view_quotation()` — the documented escape hatch `_shell()` uses.
    #   At module level it is a cycle: `purchase.py` imports this module for the
    #   document formatters. The pair is listed here so the in-function import
    #   is a pinned decision rather than an omission from this table.
    ("quotation", "purchase",  "module", "purchase.py imports quotation.py for the document "
                                         "formatters, so a module-level import back is a "
                                         "cycle. view_quotation() imports it in the function "
                                         "body to call job_cost(), which is the one "
                                         "definition of `committed`"),
    ("proforma",  "invoice",   "any", "same rule, one link further down"),
    ("purchase",  "proforma",  "any", "the buy side must never touch a sell-side money document"),
    ("purchase",  "invoice",   "any", "a PO records input tax; an invoice records output tax"),
    ("proforma",  "purchase",  "any", "and the sell side must never reach across either"),
    ("invoice",   "purchase",  "any", "same"),

    # ── The buy side reaches UP the BOQ chain, and no further (Pass C) ──────
    #
    # `/purchase/from-boq/<id>` and `/purchase/from-draft/<id>` gave the real
    # purchase order an upstream, which is what finally puts procurement cost on
    # a project. What it must NOT give it is a dependency on any other document
    # module: `purchase.py` may read a schedule and render its picker, and that
    # is the whole of it.
    #
    # `po_draft` is the load-bearing one and it runs both ways. The conversion
    # route lives in `purchase.py` because it writes a `purchases` record;
    # `po_draft.py` links to it with `url_for` and reads `converted_po_ids` off
    # its own record. If either imported the other, two sibling document modules
    # would be coupled for the sake of one dict lookup — which is exactly what
    # the one-way trick between quotation/proforma, proforma/invoice,
    # quotation/purchase, boq/ra, ra/receipt and boq/challan exists to avoid.
    ("purchase", "po_draft", "any", "the conversion route lives in purchase.py because it "
                                    "writes a purchases record; po_draft.py links to it by "
                                    "URL and reads STORE['purchase_orders'] is read the "
                                    "other way — neither imports the other"),
    ("purchase", "ra",       "any", "an RA bill claims money IN against a schedule; a PO "
                                    "commits money OUT. They share a BOQ and nothing else"),
    ("purchase", "challan",  "any", "a goods-movement note is not a purchase order"),
    ("purchase", "receipt",  "any", "a receipt is money RECEIVED — the other side of the "
                                    "ledger entirely"),
    ("purchase", "charge",   "any", "an employee expense is not a purchase order"),
    ("purchase", "client",   "any", "client segregation is a sell-side ledger"),
    ("purchase", "spec",     "any", "the BOQ already copied the clause it needs"),

    # ── The BOQ chain (handover §3.4) ───────────────────────────────────────
    ("boq", "ra",       "any", "the BOQ view page links out with url_for and reads STORE['ra_bills'] "
                               "directly — importing ra.py back would be a cycle"),
    ("boq", "proforma", "any", "a BOQ has no proforma; it bills through RA"),
    ("boq", "invoice",  "any", "the RA bill carries the tax block per DOMAIN.md §4, not the BOQ — boq does not import invoice"),
    ("boq", "purchase", "any", "a BOQ does not link to a purchase order"),
    ("boq", "settings", "any", "settings imports quotation; nothing downstream of it may import back"),
    ("boq", "product",  "any", "the BOQ picker reads the SPEC library. product.py serves the "
                               "quotation chain and its base_price is not a BOQ supply rate"),
    ("boq", "po_draft", "any", "the BOQ view page links out with url_for and reads STORE['purchase_orders'] "
                               "directly — importing po_draft.py back would be a cycle"),

    # ── Draft POs from BOQ (Phase 4 / Item 4) ───────────────────────────────
    ("po_draft", "purchase", "any", "the buy-side PO computes GST and numbers through an "
                                    "FY-scoped series; a draft PO does neither. Separate "
                                    "behaviour — the shared APPEARANCE comes from docsheet.py"),
    ("po_draft", "ra",       "any", "Draft POs do not need to know about Running Account bills"),
    ("po_draft", "invoice",  "any", "Draft POs have no tax block and no relation to tax invoices"),
    ("po_draft", "proforma", "any", "Draft POs have no relation to proformas"),
    ("po_draft", "receipt",  "any", "nor to money received"),
    ("po_draft", "client",   "any", "nor to the client ledger"),
    ("po_draft", "product",  "any", "a draft PO is written from the BOQ, not the catalogue — "
                                    "and it must not read a buy rate from anywhere"),
    ("settings", "po_draft", "any", "settings.py owns the SERIES and knows nothing about the "
                                    "document; po_draft.py reads it, never the reverse"),

    # ── The BOQ line picker is a LEAF (CLIENT_CHANGES.md item 5) ────────────
    #
    # `boqpick.py` holds the grid two documents render and a third will: the
    # checkbox rows, the family fold, the tools bar and the payload parser. It
    # is the same shape of extraction as `docsheet.py` and it is a leaf for the
    # same reason — if it could import either consumer, `po_draft.py` and
    # `challan.py` would be coupled through the basement while appearing not to
    # be. It renders no document and owns no route.
    ("boqpick", "po_draft",  "any", "the picker is a leaf: po_draft.py renders THROUGH it"),
    ("boqpick", "challan",   "any", "same — challan.py renders through it"),
    ("boqpick", "ra",        "any", "the claim grid is ra.py's own and stays there; "
                                    "it carries the over-claim guard and money columns"),
    ("boqpick", "docsheet",  "any", "a form is not a printed sheet"),
    ("boqpick", "invoice",   "any", "the picker has nothing to do with any document"),
    ("boqpick", "proforma",  "any", "same"),
    ("boqpick", "purchase",  "any", "same"),
    ("boqpick", "receipt",   "any", "same"),
    ("boqpick", "client",    "any", "same"),
    ("boqpick", "product",   "any", "the picker reads a BOQ, never the catalogue"),
    ("boqpick", "spec",      "any", "the BOQ already copied the clause it needs"),
    ("boqpick", "settings",  "any", "settings.py imports quotation; nothing downstream "
                                    "may import back"),
    ("boqpick", "flask",     "any", "it builds HTML strings and owns no route"),
    ("boq",     "boqpick",   "any", "boqpick.py imports boq.py for _line_id and the "
                                    "rest; importing back is a cycle"),

    # ── Delivery challans (CLIENT_CHANGES.md item 5) ────────────────────────
    #
    # The load-bearing one is `challan -> ra`. A DC records goods leaving the
    # yard; an RA bill records money claimed. They diverge in both directions
    # on a real site — material dispatched and not yet billed, material billed
    # and not yet dispatched — and coupling them would force one to answer the
    # other's questions. Nothing reconciles them, and that is ABOUT.md §7 gap
    # 19 rather than a thing this module should close on its own.
    ("challan", "ra",        "any", "a challan records goods moved, an RA bill records "
                                    "money claimed; they diverge and neither answers "
                                    "the other's questions"),
    ("challan", "invoice",   "any", "a challan has no tax block and no relation to a "
                                    "tax invoice"),
    ("challan", "proforma",  "any", "the PI belongs to the quotation chain"),
    ("challan", "purchase",  "any", "the buy side is a separate pipeline"),
    ("challan", "po_draft",  "any", "two BOQ-chain documents that share a PICKER, not "
                                    "each other — both import boqpick.py"),
    ("challan", "quotation", "any", "the form furniture is read through docsheet.py, "
                                    "which is the leaf both this module and the sell "
                                    "chain depend on"),
    ("challan", "product",   "any", "a challan is written from the BOQ, not the catalogue"),
    ("challan", "receipt",   "any", "a goods movement is not a payment"),
    ("challan", "client",    "any", "nor a client ledger"),
    ("challan", "spec",      "any", "the BOQ already copied the clause"),
    ("boq",     "challan",   "any", "the BOQ view page links out with url_for and reads "
                                    "STORE['delivery_challans'] directly — importing "
                                    "challan.py back would be a cycle"),
    ("settings", "challan",  "any", "settings.py owns the SERIES and knows nothing about "
                                    "the document; challan.py reads it, never the reverse"),
    ("docsheet", "challan",  "any", "the sheet is a leaf: challan.py renders through it"),
    ("docsheet", "boqpick",  "any", "the printed sheet knows nothing about a form"),

    # ── RA billing (Phase 4) ────────────────────────────────────────────────
    ("ra", "proforma", "any", "an RA bill is a claim against a BOQ; the PI belongs to "
                              "the quotation chain and has nothing to say about it"),
    ("ra", "invoice",  "any", "an RA bill computes its own per-line tax block per DOMAIN.md §4; "
                              "invoice.py is the sell chain's document-level tax and must not be imported"),
    ("ra", "purchase", "any", "the buy side is a separate pipeline"),
    ("ra", "product",  "any", "a BOQ line is a clause of work, not a catalogue item; "
                              "base_price is not a claim rate"),
    ("ra", "spec",     "any", "the spec library is what a BOQ is WRITTEN from; a claim "
                              "is measured against the BOQ, which already copied it"),

    # ── The measurement sheet (CC-2 C2 / C1, 29 August 2026) ────────────────
    #
    # ⚠ **`measurement -> ra` is the load-bearing one.** `ra.py` imports THIS
    #   module for `approved_qty_by_line()`, which is CC-2's own sentence in
    #   code — *"approved measurements become the source of installation
    #   quantity on RA-Installation."* The arrow runs one way; importing back is
    #   a cycle at boot. `measurement.py` links out with `url_for` and reads
    #   nothing of `ra.py`'s, exactly as `boq.py` does.
    ("measurement", "ra",        "any", "ra.py imports THIS module for the "
                                        "approved measured quantity; importing "
                                        "back is a cycle"),
    # ⚠ **`ra -> challan` is refused in BOTH directions, and C1 did not change
    #   that.** The supply leg's C1 guard needs one question — does a challan
    #   exist on this chain — and `ra.challan_exists()` answers it by reading
    #   `STORE["delivery_challans"]` directly, the one-way trick used between
    #   boq/ra, boq/challan and ra/receipt. The stated reason for the existing
    #   `challan -> ra` prohibition ("they diverge and neither answers the
    #   other's questions") cuts both ways, and an existence check is not a
    #   reason to couple two document modules.
    ("ra",          "challan",   "any", "the supply leg's C1 guard reads "
                                        "STORE['delivery_challans'] directly; "
                                        "coupling the two modules is what the "
                                        "challan -> ra prohibition already "
                                        "refuses from the other side"),
    ("measurement", "challan",   "any", "the two legs of C1 are separate: a "
                                        "challan proves goods moved, a "
                                        "measurement proves work was done, and "
                                        "neither answers the other"),
    ("measurement", "receipt",   "any", "a measurement is not a payment"),
    ("measurement", "invoice",   "any", "a measurement has no tax block and no "
                                        "relation to a tax invoice"),
    ("measurement", "proforma",  "any", "the PI belongs to the quotation chain"),
    ("measurement", "purchase",  "any", "the buy side is a separate pipeline"),
    ("measurement", "po_draft",  "any", "two BOQ-chain documents that share a "
                                        "PICKER, not each other"),
    ("measurement", "quotation", "any", "the form furniture is read through "
                                        "docsheet.py, which is the leaf both "
                                        "this module and the sell chain depend "
                                        "on"),
    ("measurement", "product",   "any", "a measurement is written from the BOQ, "
                                        "not the catalogue"),
    ("measurement", "client",    "any", "a measurement is not a client ledger"),
    ("measurement", "spec",      "any", "the BOQ already copied the clause"),
    ("measurement", "settings",  "any", "settings.py imports quotation; nothing "
                                        "downstream of it may import back. The "
                                        "measurement series is FY-scoped "
                                        "through pipeline.fy_ref and owns no "
                                        "/settings counter"),
    ("measurement", "employee",  "any", "who measured is a name on the sheet, "
                                        "not a link to the employee master"),
    ("measurement", "attendance", "any", "and emphatically not to the muster — "
                                         "C6 is BLOCKED"),
    ("measurement", "project",   "any", "measurement.py reads STORE['boqs'] and "
                                        "links out with url_for"),
    ("measurement", "auth",      "any", "the gate is central "
                                        "(auth.ROUTE_PERMISSIONS) and no page "
                                        "module asks it directly"),
    ("boq",         "measurement", "any", "the BOQ view page links out with "
                                          "url_for and reads STORE['measurements'] "
                                          "directly — importing measurement.py "
                                          "back would be a cycle"),
    ("boqpick",     "measurement", "any", "the picker is a leaf: measurement.py "
                                          "renders THROUGH it, at its FOURTH "
                                          "consumer"),
    ("docsheet",    "measurement", "any", "the sheet is a leaf: measurement.py "
                                          "renders through it"),
    ("challan",     "measurement", "any", "and the same edge from the other "
                                          "side"),

    # ── Receipts (CLIENT_CHANGES.md item 8) ─────────────────────────────────
    # The load-bearing one is `ra -> receipt`. `receipt.py` imports `ra.py` for
    # the bill and the balance arithmetic, so importing back is a cycle — and
    # the arithmetic lives in ra.py precisely because `create_ra()` needs the
    # carried balance at save time. ra.py's receipts panel reads
    # STORE["receipts"] directly and links out with url_for instead.
    ("ra", "receipt",  "any", "receipt.py imports ra.py; ra.py reads STORE['receipts'] "
                              "directly and links out with url_for, which is what keeps "
                              "the arrow one-way"),
    ("boq", "receipt", "any", "a BOQ knows nothing about payments — they are keyed to "
                              "an RA bill, and boq.py may not import ra.py either"),
    ("spec", "receipt", "any", "a specification clause knows nothing about money received"),
    ("receipt", "invoice",  "any", "a receipt settles an RA bill in the BOQ chain; "
                                   "invoice.py is the sell chain's tax document"),
    ("receipt", "proforma", "any", "the PI belongs to the quotation chain"),
    ("receipt", "purchase", "any", "the buy side is a separate pipeline — that is money OUT"),
    ("receipt", "product",  "any", "a payment has nothing to do with the catalogue"),
    ("receipt", "spec",     "any", "nor with the specification library"),

    # ── Client Segregation (CLIENT_CHANGES.md item 2) ───────────────────────
    ("boq", "client", "any", "the BOQ knows nothing about client segregation"),
    ("client", "invoice", "any", "client segregation uses RA claims, not invoices"),
    ("client", "proforma", "any", "the PI belongs to the quotation chain"),
    ("client", "purchase", "any", "the buy side is a separate pipeline"),
    ("client", "product", "any", "a client page has nothing to do with the catalogue"),
    ("client", "spec", "any", "a client page has nothing to do with the specification library"),

    # ── Employee & miscellaneous charges (CLIENT_CHANGES.md item 9) ──────
    ("charge", "boq",       "any", "a charge is not part of the BOQ chain"),
    ("charge", "ra",        "any", "a charge is not an RA bill"),
    ("charge", "receipt",   "any", "a charge is not a payment received"),
    ("charge", "invoice",   "any", "a charge is not a tax invoice"),
    ("charge", "proforma",  "any", "a charge is not a proforma"),
    ("charge", "purchase",  "any", "a charge is not a purchase order"),
    ("charge", "po_draft",  "any", "a charge is not a draft PO"),
    ("charge", "challan",   "any", "a charge is not a delivery challan"),
    ("charge", "product",   "any", "a charge is not a catalogue item"),
    ("charge", "spec",      "any", "a charge is not a specification"),
    ("charge", "docsheet",  "any", "a charge is not a printed document"),
    ("charge", "boqpick",   "any", "a charge does not pick BOQ lines"),
    ("charge", "client",    "any", "a charge is not client segregation"),
    ("charge", "settings",  "any", "settings.py imports quotation; nothing downstream may import back"),
    ("charge", "project",   "any", "a charge reads STORE['projects'] directly"),

    # ── The employee master is a LEAF (CC-2 C4, 29 August 2026) ─────────────
    #
    # `employee.py` holds people and what they are paid. It renders no document
    # and belongs to no chain, so it may reach for the chrome and nothing else —
    # exactly `charge.py`'s position, one collection along.
    #
    # ⚠ **`employee` <-> `charge` is forbidden in BOTH directions, and that is
    #   the load-bearing pair.** Linking the wages ledger to the employee master
    #   is CC-2 **C5** (attendance and site-wise labour cost), which is GATED and
    #   was not authorised by the 29 August override block. `charge.person` stays
    #   free text. The edge would be the whole of C5's first step, so it is
    #   refused at AST level rather than left to a comment.
    ("employee", "charge",    "any", "linking the wages ledger to the employee "
                                     "master is C5, which is gated"),
    ("charge",   "employee",  "any", "and the same edge from the other side"),
    ("employee", "boq",       "any", "an employee is not part of the BOQ chain"),
    ("employee", "ra",        "any", "an employee is not an RA bill"),
    ("employee", "receipt",   "any", "an employee is not a payment received"),
    ("employee", "invoice",   "any", "an employee is not a tax invoice"),
    ("employee", "proforma",  "any", "an employee is not a proforma"),
    ("employee", "purchase",  "any", "an employee is not a purchase order"),
    ("employee", "po_draft",  "any", "an employee is not a draft PO"),
    ("employee", "challan",   "any", "an employee is not a delivery challan"),
    ("employee", "product",   "any", "an employee is not a catalogue item"),
    ("employee", "spec",      "any", "an employee is not a specification"),
    ("employee", "docsheet",  "any", "an employee record never prints — there is "
                                     "no document here and no sheet to render on"),
    ("employee", "boqpick",   "any", "an employee does not pick BOQ lines"),
    ("employee", "client",    "any", "an employee is not a client"),
    ("employee", "project",   "any", "linking a person to a project is C5/C6, "
                                     "both gated"),
    ("employee", "settings",  "any", "settings.py imports quotation; nothing "
                                     "downstream may import back"),
    ("employee", "auth",      "any", "the gate is central (auth.ROUTE_PERMISSIONS) "
                                     "and no page module asks it directly"),

    # ── The spec library ────────────────────────────────────────────────────
    ("spec", "boq",      "any", "boq.py imports THIS module for the picker; importing back is a cycle"),
    ("spec", "product",  "any", "spec.py replaces nothing in product.py and must not depend on it"),
    ("spec", "quotation", "any", "the library is not part of the quotation chain"),
    ("spec", "ra",       "any", "a spec knows nothing about billing"),

    # ── The shared document sheet is a LEAF ─────────────────────────────────
    #
    # `docsheet.py` holds the printed chrome — letterhead, party block, table
    # shell, totals rows, bank block, signature — that six documents used to
    # each write their own copy of. It may import the A4 stylesheet and the
    # money formatters; it may not import any module that renders a document
    # through it.
    #
    # This is the half that preserves the standing rule. `ra.py` may never
    # import `invoice.py` (the RA tax block is per line with HSN/SAC, the sell
    # chain's is document-level) — and after the extraction neither imports the
    # other. **Both import the leaf.** If `docsheet` were allowed to import
    # either one, that prohibition would be satisfied on paper and defeated in
    # practice, because the coupling would simply run through the basement.
    ("docsheet", "invoice",   "any", "the sheet is a leaf: invoice.py renders THROUGH it"),
    ("docsheet", "proforma",  "any", "same — proforma.py renders through it"),
    ("docsheet", "purchase",  "any", "same — purchase.py renders through it"),
    ("docsheet", "ra",        "any", "same — ra.py renders through it, and this is the "
                                     "arrow that keeps ra.py and invoice.py apart"),
    ("docsheet", "boq",       "any", "same"),
    ("docsheet", "po_draft",  "any", "same"),
    ("docsheet", "receipt",   "any", "a payment is not a printed document"),
    ("docsheet", "client",    "any", "nor is a client ledger"),
    ("docsheet", "product",   "any", "the sheet has nothing to do with the catalogue"),
    ("docsheet", "spec",      "any", "nor with the specification library"),
    ("docsheet", "settings",  "any", "settings.py imports quotation; nothing downstream may import back"),
    ("docsheet", "flask",     "any", "it builds HTML strings and owns no route"),

    # ── demo_data is data only and sits at the bottom of the graph ──────────
    ("demo_data", "store",     "any", "demo_data.py imports NOTHING from the app — that is what "
                                      "lets spec.py and boq.py both read it without a cycle"),
    ("demo_data", "spec",      "any", "same"),
    ("demo_data", "boq",       "any", "same"),
    ("demo_data", "branding",  "any", "same"),
    ("demo_data", "pipeline",  "any", "same"),
    ("demo_data", "dashboard", "any", "same"),
    ("demo_data", "flask",     "any", "it is a data module, not a Flask one"),

    # ── The project entity is a LEAF (Pass A) ────────────────────────────
    #
    # project.py holds the commercial engagement BOQs are grouped under.
    # It is a leaf: it may import dashboard, pipeline, store and branding,
    # and nothing else from the app.  boq.py reads STORE["projects"]
    # directly and links out with url_for — the same one-way trick used
    # between boq→ra, boq→challan, boq→po_draft, and ra→receipt.
    #
    # Nothing imports project.py at module level.  That is what keeps the
    # graph acyclic: project sits beside client, both above dashboard and
    # below the document chain.
    ("project", "boq",       "any", "project.py is a leaf; boq.py reads STORE['projects'] "
                                    "directly and links out with url_for"),
    ("project", "challan",   "any", "a project does not know about challans"),
    ("project", "purchase",  "any", "the buy side is a separate pipeline"),
    ("project", "po_draft",  "any", "a project does not know about draft POs"),
    ("project", "invoice",   "any", "a project does not know about tax invoices"),
    ("project", "ra",        "any", "a project does not know about RA bills"),
    ("project", "receipt",   "any", "a project does not know about payments"),
    ("project", "quotation", "any", "a project does not know about quotations"),
    ("project", "product",   "any", "a project is not part of the catalogue"),
    ("project", "docsheet",  "any", "a project is not a printed document"),
    ("project", "boqpick",   "any", "a project does not pick BOQ lines"),
    ("project", "spec",      "any", "a project is not a specification"),
    ("project", "client",    "any", "client segregation is a separate concern"),
    ("project", "settings",  "any", "settings.py imports quotation; nothing downstream "
                                    "may import back"),

    # ⚠ The two reverses of the arrows added on 30 August 2026 (fourth pass).
    #   `project.py -> address.py` and `projectview.py -> project.py` both
    #   exist and are in REQUIRED below; these are what stop either becoming a
    #   cycle at boot.
    ("address", "project",   "any", "project.py imports address.py for the SITE "
                                    "picker and SITE_TYPES. address.py reads "
                                    "STORE['projects'] DIRECTLY for "
                                    "references_of() — the one-way trick, and it "
                                    "has to be: five other modules import "
                                    "address.py, so an import back from it "
                                    "would put project.py under all of them"),
    ("project", "projectview", "any", "projectview.py imports project.py for "
                                      "site_drift(); the reverse is a cycle"),

    # ── auth.py sits at the BOTTOM of the graph (Phase 3B) ───────────────
    #
    # It has to, because it is imported by `dashboard.py` — which every other
    # module imports for `BASE_STYLES` and `_nav()`. Anything auth.py pulled in
    # at module level would therefore be pulled in by the whole application.
    #
    # `dashboard` is "module" rather than "any" for exactly the reason
    # `dashboard -> product` is: `auth._shell()` imports the chrome inside the
    # function body, which breaks the cycle and is deliberate. At module level
    # it would be a boot failure.
    ("auth", "dashboard", "module", "dashboard.py imports auth.py for the Access card, "
                                    "so a module-level import back is a cycle. "
                                    "auth._shell() imports the chrome in the function "
                                    "body — the precedent dashboard.index() sets"),
    ("auth", "quotation", "module", "same cycle, one further out: quotation.py imports "
                                    "dashboard.py. QUOTATION_STYLES is pulled in "
                                    "beside BASE_STYLES inside _shell()"),
    ("auth", "docsheet",  "any",    "auth.py renders no document. Nothing that prints "
                                    "may be reachable from the bottom of the graph"),
    ("auth", "boq",       "any",    "identity knows nothing about a schedule"),
    ("auth", "ra",        "any",    "identity knows nothing about a claim"),
    ("auth", "invoice",   "any",    "identity knows nothing about a tax invoice"),
    ("auth", "purchase",  "any",    "identity knows nothing about the buy side"),
    ("auth", "settings",  "any",    "settings.py imports quotation, which imports "
                                    "dashboard, which imports auth"),
    ("auth", "product",   "any",    "and product.py is one of the two frozen files"),
    ("auth", "db",        "any",    "auth.py mutates STORE like every other module; "
                                    "db.py mirrors it. It must not reach for the "
                                    "database itself"),
]


@pytest.mark.parametrize("module,forbidden,scope,why", FORBIDDEN)
def test_module_does_not_import(module, forbidden, scope, why):
    if not (REPO / f"{module}.py").exists():
        pytest.skip(f"{module}.py does not exist yet")
    found = imports_of(module, top_level_only=(scope == "module"))
    where = " at module level" if scope == "module" else ""
    assert forbidden not in found, (
        f"{module}.py must not import {forbidden}.py{where} — {why}"
    )


# ── The directions that must EXIST ──────────────────────────────────────────
REQUIRED = [
    ("boq", "quotation", "the document toolkit — _inr, _fmt_qty, _amount_in_words, "
                         "_meta, VIEW_DOC_STYLES, QUOTATION_STYLES"),
    ("boq", "dashboard", "BASE_STYLES and _nav"),
    ("boq", "pipeline",  "esc / parse_money / fy_of / fy_ref"),
    ("boq", "address",   "the customer picker"),
    ("boq", "spec",      "the specification library — what the line picker is built from"),
    ("boq", "demo_data", "the seed table behind ensure_demo_boq()"),
    ("boq", "store",     "the shared STORE dict"),
    ("boq", "branding",  "every company string, colour and image"),

    ("dashboard", "db", "_nav() renders the persistence-failure strip, and _nav() is "
                        "the only thing in this app that is on every page"),

    ("ra", "boq",      "the schedule a claim is measured against, plus "
                       "_line_id / _item_no / _num — and _line_id is the key a "
                       "claim is matched on"),
    ("ra", "pipeline", "esc / parse_money / fy_of / fy_ref"),
    ("ra", "store",    "the shared STORE dict"),
    ("ra", "branding", "COMPANY_SHORT for the document series"),
    ("ra", "dashboard", "BASE_STYLES and _nav — the entry form is a page in the "
                        "app, so it carries the same chrome and the same "
                        "persistence-failure strip as every other page"),
    ("ra", "quotation", "QUOTATION_STYLES and _inr — the form widgets, so the "
                        "RA form IS the BOQ form. Emphatically NOT _tax_lines: "
                        "an RA bill is a claim document, and "
                        "test_ra_record.py asserts that absence at AST level"),

    ("receipt", "ra",        "the bill a payment is against, the revision chain, and "
                             "the balance arithmetic — received_against / outstanding_of "
                             "/ previous_balance, which live in ra.py so that "
                             "create_ra() can snapshot without importing downstream"),
    ("receipt", "boq",       "BOQ_STYLES, so the receipt form is the same form"),
    ("receipt", "quotation", "QUOTATION_STYLES and _inr — the form widgets"),
    ("receipt", "dashboard", "BASE_STYLES and _nav"),
    ("receipt", "pipeline",  "esc / parse_money / fy_of / fy_ref"),
    ("receipt", "store",     "the shared STORE dict"),
    ("receipt", "branding",  "COMPANY_SHORT for the document series"),

    ("spec", "dashboard", "BASE_STYLES and _nav"),
    ("spec", "pipeline",  "esc"),
    ("spec", "store",     "the shared STORE dict"),
    ("spec", "branding",  "every company string, colour and image"),
    ("spec", "demo_data", "the 56 seeded clauses"),

    ("client", "boq",       "boq_identity, BOQ_STYLES"),
    ("client", "ra",        "bills_of, is_issued, is_cancelled"),
    ("client", "receipt",   "receipts_of_boq"),
    ("client", "quotation", "QUOTATION_STYLES and _inr"),
    ("client", "dashboard", "BASE_STYLES and _nav"),
    ("client", "pipeline",  "esc / norm_name"),
    ("client", "store",     "the shared STORE dict"),
    ("client", "branding",  "every company string, colour and image"),

    ("charge", "dashboard", "BASE_STYLES and _nav"),
    ("charge", "pipeline",  "esc"),
    ("charge", "store",     "the shared STORE dict"),
    ("charge", "branding",  "every company string, colour and image"),
    ("charge", "quotation", "QUOTATION_STYLES"),

    ("employee", "dashboard", "BASE_STYLES, _nav and rupees"),
    ("employee", "pipeline",  "esc and parse_money"),
    ("employee", "store",     "the shared STORE dict"),
    ("employee", "branding",  "every company string, colour and image"),
    ("employee", "quotation", "QUOTATION_STYLES"),
    ("employee", "address",   "the SITE picker over the shared address book "
                              "(30 August 2026). `site` was free text on this "
                              "record and on an attendance marking, which is "
                              "why the live data spells one place more than "
                              "one way. `po_draft.py` and `challan.py` already "
                              "reach the same book the same way, and "
                              "`attendance.py` reads the picker THROUGH this "
                              "module rather than importing the book twice — "
                              "one arrow, one definition, so the two forms "
                              "cannot describe one field differently"),

    # ── The shared document sheet, and everything that renders through it ────
    ("docsheet", "quotation", "VIEW_DOC_STYLES and the document's own money "
                              "formatters. quotation.py is frozen against EDITS "
                              "(INTRODUCTION.md §7), not against being depended "
                              "on — boq, ra and purchase all import it already"),
    ("docsheet", "dashboard", "BASE_STYLES, the first sheet in the stack"),
    ("docsheet", "pipeline",  "esc, and PIPELINE_STYLES for the stack"),
    ("docsheet", "branding",  "the company identity the letterhead is built from"),

    ("invoice",  "docsheet", "the letterhead, party block, table shell, totals "
                             "rows and signature — one copy, not four"),
    ("proforma", "docsheet", "the same sheet, plus the bank block it used to own"),
    ("purchase", "docsheet", "the same sheet. The buy side shares the CHROME "
                             "with the sell side and nothing else — no tax "
                             "arithmetic and no business logic cross this arrow"),
    ("ra",       "docsheet", "the same sheet again, and THIS is the arrow that "
                             "lets the RA bill carry the tax invoice's "
                             "letterhead without ra.py importing invoice.py"),

    ("po_draft", "docsheet", "the same sheet as the buy-side PO — separate "
                             "behaviour, shared appearance"),
    ("po_draft", "boq",      "superseded_ids, _line_id, _item_no, _num, _fmt_qty "
                             "— and _line_id is the key a picked line is matched on"),
    ("po_draft", "settings", "the ONE running number series, editable at /settings. "
                             "settings.py owns it and imports nothing back"),
    ("po_draft", "address",  "the vendor picker over the shared address book"),
    ("po_draft", "dashboard", "BASE_STYLES and _nav"),
    ("po_draft", "pipeline",  "esc"),
    ("po_draft", "store",     "the shared STORE dict"),
    ("po_draft", "branding",  "every company string, colour and image"),

    ("boqpick", "boq",      "_line_id / _item_no / _num / _fmt_qty / "
                            "_json_for_script / MAX_LINES — and _line_id is the "
                            "key a picked line is matched on"),
    ("boqpick", "pipeline", "esc"),

    ("po_draft", "boqpick", "the line picker, extracted at the SECOND consumer "
                            "rather than the fourth. `/po/create` is pinned "
                            "byte-for-byte across that move in "
                            "tests/test_print_golden.py"),

    # ── The buy side's own arrows up the BOQ chain (Pass C) ─────────────────
    ("purchase", "boq",     "superseded_ids — a superseded schedule is refused at "
                            "the route, not merely unlinked — plus _line_id, "
                            "_item_no, _num, _fmt_qty and MAX_LINES"),
    ("purchase", "boqpick", "the line picker, at its THIRD consumer. It was "
                            "extracted so this grid would not be written a third "
                            "time, and importing it is what makes that true"),

    ("challan", "boqpick",  "the same grid — the challan is the second consumer "
                            "the extraction was made for"),
    ("challan", "docsheet", "the same A4 sheet as every other document that "
                            "prints, and THIS is the arrow that lets the challan "
                            "carry the tax invoice's letterhead without importing "
                            "invoice.py — or quotation.py, which is on its own "
                            "prohibited list"),
    ("challan", "boq",      "superseded_ids, _line_id, _item_no, _fmt_qty and "
                            "_ancestor_ids — the revision chain the cumulative "
                            "dispatched quantity is summed across"),
    ("challan", "settings", "the ONE running number series, editable at /settings. "
                            "settings.py owns it and imports nothing back"),
    ("challan", "address",  "the consignee prefill over the shared address book"),
    ("challan", "dashboard", "BASE_STYLES and _nav"),
    ("challan", "pipeline",  "esc and gstin_state_label — the seller's State is "
                             "DERIVED from the GSTIN, never stored beside it"),
    ("challan", "store",     "the shared STORE dict"),
    ("challan", "branding",  "every company string, colour and image"),

    # ── The measurement sheet (CC-2 C2, 29 August 2026) ──────────────────
    #
    # ⚠ **`ra -> measurement` is the arrow CC-2 states in its own words** —
    #   "approved measurements become the source of installation quantity on
    #   RA-Installation". It is the ONLY arrow into this module from a document
    #   module, and `measurement.py` imports none of them back.
    ("ra", "measurement", "approved_qty_by_line() and has_approved_measurement() "
                          "— the installation ceiling and C1's ordering guard. "
                          "This is CC-2 C2's own sentence in code and the reason "
                          "measurement.py may never import ra.py"),
    ("measurement", "boq",      "superseded_ids, _line_id, _item_no, _fmt_qty and "
                                "_ancestor_ids — the revision chain the "
                                "cumulative measured quantity is summed across"),
    ("measurement", "boqpick",  "the same grid, at its FOURTH consumer. It was "
                                "extracted so this would not be written a fourth "
                                "time, and importing it is what makes that true"),
    ("measurement", "docsheet", "the same A4 sheet as every other document that "
                                "prints — NOTHING new was drawn for this "
                                "document, which is what CC-2's silence on its "
                                "appearance required"),
    ("measurement", "approval", "the ladder (B6). measurement.py is the fifth "
                                "entry in approval.DOCUMENTS and calls "
                                "can_print / can_modify / panel like the other "
                                "four"),
    ("measurement", "dashboard", "BASE_STYLES and _nav"),
    ("measurement", "pipeline",  "esc, fy_of, fy_ref and gstin_state_label — the "
                                 "seller's State is DERIVED from the GSTIN, "
                                 "never stored beside it"),
    ("measurement", "store",     "the shared STORE dict"),
    ("measurement", "branding",  "every company string, colour and image"),

    # ── project.py is a LEAF (Pass A) ────────────────────────────────────
    ("project", "dashboard", "BASE_STYLES and _nav"),
    ("project", "pipeline",  "esc / norm_name"),
    ("project", "store",     "the shared STORE dict"),
    ("project", "branding",  "every company string, colour and image"),
    ("project", "address",   "the SITE picker over the shared address book "
                             "(30 August 2026, fourth pass). `site_address` was "
                             "free text on this record, which is why the live "
                             "data spells one place two ways — and a project's "
                             "site is a JOIN KEY, which free text cannot be. "
                             "⚠ `SITE_TYPES` is read from address.py and never "
                             "redefined here: two pickers that can disagree "
                             "about what counts as a site is the defect, and "
                             "employee.py reads the same tuple from the same "
                             "place. address.py does NOT import back — it reads "
                             "STORE['projects'] directly, the one-way trick"),

    ("projectview", "project", "site_drift() — where the label snapshot and the "
                               "live address have come apart. The drift belongs "
                               "to the module that WRITES both copies, for the "
                               "reason party_drift() lives in ra.py; a second "
                               "copy of the resolve-a-label rule here is the "
                               "SITE_TYPES defect one level up"),

    # ── ⚠ THE ONE ARROW INTO attendance.py, and it did not exist until the
    #    FIFTH override block of 30 August 2026 ────────────────────────────
    ("projectview", "attendance", "marking_cells() and markings_at_site(), for "
                                  "the Site Labour section. ⚠ NOTHING imported "
                                  "attendance.py until 30 August 2026 and this "
                                  "is still the ONLY module that may — "
                                  "test_attendance.py holds it as an ALLOWLIST "
                                  "OF ONE rather than a blacklist. The arrow "
                                  "belongs to projectview.py rather than "
                                  "project.py because the module that RENDERS "
                                  "the section owns it, exactly as the arrow to "
                                  "ra.py for revision_chain() does; putting it "
                                  "on project.py would pull employee.py and "
                                  "settings.py into the import graph of every "
                                  "future reader of the project entity, for a "
                                  "section project.py does not draw. ⚠ What "
                                  "crosses is RENDERED CELLS, never the "
                                  "arithmetic: C6 is BLOCKED on CC-2's Open "
                                  "question 4, and a second module able to "
                                  "compute a wage is a second place the OT "
                                  "multiplier could be hardcoded"),
    ("projectview", "settings", "ot_multiplier(), passed straight through to "
                                "attendance.marking_cells(). ⚠ Read here rather "
                                "than inside attendance.py because CC-2 requires "
                                "the multiplier to be a SETTING and ot_amount() "
                                "takes it as an argument for that reason — this "
                                "page fetches it the same way /attendance/ does "
                                "and performs no arithmetic of its own"),

    # ── auth.py — the whole of what it may reach for (Phase 3B) ──────────
    ("auth", "store",    "the shared STORE dict — users and roles are two "
                         "collections in it, like every other record"),
    ("auth", "pipeline", "esc. pipeline.py imports nothing from the app, which "
                         "is what makes it safe from the bottom of the graph"),
    ("auth", "branding", "the logo and company name on the login page"),
]


def test_db_imports_nothing_from_the_app():
    """
    What makes `dashboard.py -> db.py` safe.

    dashboard.py sits at the bottom of the graph and is imported BY every other
    module, so anything it imports must import nothing of ours. db.py qualifies
    — pymysql, dotenv and the standard library — and it has to keep qualifying,
    because the persistence strip in `_nav()` is now on every page in the app.
    """
    ours = {m.stem for m in REPO.glob("*.py")} - {"db"}
    assert imports_of("db") & ours == set()


def test_demo_data_imports_nothing_at_all():
    """
    The strongest form of the rule, and the reason the seed data was pulled out
    of `spec.py` and `boq.py`: a module that imports nothing can be imported by
    anything, so it sits at the bottom of the graph beside `pipeline.py` and
    `branding.py` and can never be the cause of a cycle.
    """
    assert imports_of("demo_data") == set()


def test_po_parts_imports_nothing_at_all():
    """
    `po_parts.py` is the second module held to `demo_data.py`'s standard, and
    for the same reason: it is a **data table**, not a component.

    It holds the seeded prefill list for extra purchase-order lines — every
    figure in it an assumed placeholder — and `purchase.py` reads it. Keeping it
    at the very bottom of the graph is what makes that arrow free: a table that
    imports nothing can never be half of a cycle, whoever picks it up next.

    ⚠ It is deliberately NOT a collection in `STORE` and NOT persisted by
      `db.py`, so it must not reach for either. The 29 August 2026 override
      block records that decision: this is a typeahead prefill, not a parts
      master, and a module that imported `store` would be the first step
      towards becoming one.
    """
    assert imports_of("po_parts") == set()


def test_the_seeded_part_list_is_a_prefill_and_not_a_collection():
    """
    The shape of `po_parts.py`, asserted rather than trusted to a comment.

    `purchase.py` may read the table; nothing may write it, and it must never
    acquire the machinery of a record — no `STORE` key, no blueprint, no route.
    The client asked for free-text lines and the owner chose free text; a parts
    master is the thing this was explicitly decided against, and it would arrive
    one import at a time.
    """
    src = (REPO / "po_parts.py").read_text(encoding="utf8")
    tree = ast.parse(src)

    # No route surface. Checked on the parsed source rather than on the text,
    # so that the docstring saying "this is not a page" cannot fail the test
    # that proves it.
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "Blueprint" not in names, "a prefill table must not become a page"
    assert "route" not in names, "a prefill table must not grow a route"

    # No collection. `STORE` may be *named* in the prose — it says the table is
    # deliberately not one — but it must never be reached for in code.
    assert "STORE" not in names, "a prefill table must not become a collection"

    assert "po_parts" in imports_of("purchase"), \
        "purchase.py reads the seeded prefill list"


def test_auth_imports_nothing_that_prints():
    """
    The direction that lets **every** module import `auth.py`.

    Access control is needed at the bottom of the graph — `dashboard.py` asks it
    whether to draw the Access card, and `dashboard.py` is imported by
    everything. So `auth.py` has to be safe to import from anywhere, and that is
    only true while its own module-level imports stay inside the set that is
    already safe from there: the three bottom modules plus the standard library
    and Werkzeug.

    Stated as a whitelist rather than a blacklist on purpose. A new prohibition
    has to be remembered; a whitelist catches the import nobody thought of.
    """
    allowed = {"branding", "pipeline", "store"}
    ours = {m.stem for m in REPO.glob("*.py")} - {"auth"}
    reached = imports_of("auth", top_level_only=True) & ours
    assert reached <= allowed, (
        f"auth.py imports {sorted(reached - allowed)} at module level. Every "
        f"module in this app may import auth.py, so anything it reaches for is "
        f"reached by all of them — and anything that prints would be a cycle "
        f"through dashboard.py. Use a function-body import, as _shell() does.")


def test_dashboard_asks_auth_before_drawing_the_access_card():
    """
    The other half: `dashboard.py` really does import `auth.py`.

    The Users & Access card is the only way to reach user administration without
    typing a URL, and it is drawn only for a holder of `admin.users`. If this
    arrow ever went away the card would either vanish or, worse, show for
    everybody — CLIENT_CHANGES-2.md is explicit that shipping a feature without
    its entry point is a mistake this repo has already made once.
    """
    assert "auth" in imports_of("dashboard"), (
        "dashboard.py no longer imports auth.py, so the module strip cannot ask "
        "who is signed in")


@pytest.mark.parametrize("module,required,why", REQUIRED)
def test_module_imports(module, required, why):
    assert required in imports_of(module), (
        f"{module}.py is expected to import {required}.py for {why}"
    )


def test_boq_reads_ra_bills_without_importing_ra():
    """
    The one-way trick, verified on both halves.

    `quotation.py` links to proformas with `url_for` and reads
    `STORE["proformas"]` directly, which is what keeps that arrow one-way.
    `boq.py` does the same for RA bills, and the test checks both that the
    read is there and that the import is not.
    """
    src = (REPO / "boq.py").read_text(encoding="utf8")
    assert "ra_bills" in src, "boq.py should read STORE['ra_bills'] directly"
    assert 'url_for("ra.' in src, "boq.py should link to RA bills with url_for"
    assert "ra" not in imports_of("boq")


def test_ra_reads_receipts_without_importing_receipt():
    """
    The one-way trick, one link further down again — now five times over.

    `ra.view_ra()` renders a receipts panel and offers "Record a payment", so it
    needs both the data and the link. It takes the data straight out of
    `STORE["receipts"]` and builds the link with `url_for`, which is what lets
    `receipt.py` import `ra.py` rather than the reverse.

    That direction is not a preference. `create_ra()` has to freeze the carried
    balance at the moment a bill is saved, so the arithmetic has to sit upstream
    of the module that records the payments.
    """
    src = (REPO / "ra.py").read_text(encoding="utf8")
    assert "receipts" in src, "ra.py should read STORE['receipts'] directly"
    assert 'url_for("receipt.' in src, "ra.py should link to receipts with url_for"
    assert "receipt" not in imports_of("ra")


def test_boq_reads_challans_without_importing_challan():
    """
    The one-way trick, used a sixth time.

    `/boq/view`'s action bar offers **+ Delivery Challan** on the tip of a
    revision chain, built with `url_for` exactly as the RA links and the draft
    PO link beside it are. `boq.py` may never import a module that imports it.
    """
    src = (REPO / "boq.py").read_text(encoding="utf8")
    assert 'url_for("challan.' in src, "boq.py should link to challans with url_for"
    assert "challan" not in imports_of("boq")


def test_the_two_consumers_of_the_picker_do_not_know_about_each_other():
    """
    What the extraction is *for*, asserted directly.

    `po_draft.py` and `challan.py` render the same grid. The point of lifting
    it into a leaf is that neither has to know the other exists — if either
    imported the other, the shared component would be a shared component in
    name and a dependency in fact.
    """
    assert "challan" not in imports_of("po_draft")
    assert "po_draft" not in imports_of("challan")
    for mod in ("po_draft", "challan"):
        assert "boqpick" in imports_of(mod), f"{mod}.py no longer uses the leaf"


def test_the_picker_owns_the_grid_the_two_documents_share():
    """
    Where the functions live is what makes the import direction possible, so it
    is asserted rather than left to convention — `test_the_balance_arithmetic_
    lives_upstream_in_ra`'s argument, one module over. Moving any of these back
    into a consumer forces the other to import it.
    """
    import boqpick

    for name in ("families", "line_ids", "rows_html", "grid_html", "js",
                 "picked_lines", "PICKER_CSS"):
        assert hasattr(boqpick, name), (
            f"boqpick.{name} moved — both consumers depend on it being here")


def test_the_draft_and_the_real_po_link_without_importing_each_other():
    """
    The one-way trick, used a seventh time — and this one runs in **both**
    directions at once, which is what makes it worth its own test.

    `/purchase/from-draft/<id>` reads a draft PO out of `STORE["purchase_orders"]`
    and writes `converted_po_ids` back onto it. `/po/view` and `/po/` read that
    list and link to `/purchase/view/<id>`. Neither module imports the other, and
    neither may: they are sibling document modules with different record shapes,
    different number series and — the client constraint that created the split in
    the first place — different rules about GST.

    The route lives in `purchase.py` rather than `po_draft.py` because it writes
    a `purchases` record, and a module owns the shape it writes.
    """
    assert "po_draft" not in imports_of("purchase")
    assert "purchase" not in imports_of("po_draft")

    pur = (REPO / "purchase.py").read_text(encoding="utf8")
    assert "purchase_orders" in pur, (
        "purchase.py should read STORE['purchase_orders'] directly")
    assert 'url_for("po_draft.' in pur, (
        "purchase.py should link back to the draft with url_for")

    draft = (REPO / "po_draft.py").read_text(encoding="utf8")
    assert "converted_po_ids" in draft, (
        "po_draft.py should read the converted_po_ids purchase.py writes")
    assert 'url_for("purchase.' in draft, (
        "po_draft.py should link to the real PO with url_for")


def test_the_project_is_reached_through_the_store_and_url_for():
    """
    `project.py` is a **permitted** import for `purchase.py` and is deliberately
    not taken: the project link is one id, one name and one `url_for`, and
    nothing in `project.py`'s API is needed to carry them.

    The direction that is not optional is the reverse — `project.py` is a leaf
    and may never import `purchase.py`, which the FORBIDDEN table above already
    asserts. This is the half that says why the arrow is absent rather than
    leaving a reader to guess it was forgotten.
    """
    pur = (REPO / "purchase.py").read_text(encoding="utf8")
    assert '"projects"' in pur, "purchase.py should read STORE['projects'] directly"
    assert 'url_for("projectview.' in pur, (
        "purchase.py should link to the project's page with url_for")
    assert "purchase" not in imports_of("project")


def test_the_picker_is_shared_by_three_documents_now():
    """
    `boqpick.py` was extracted at its second consumer rather than its fourth,
    on the reasoning that three copies is where `docsheet.py` found four
    letterheads that had already drifted apart. The third consumer has arrived
    and did not write a fourth copy — which is the extraction paying for itself.
    """
    for mod in ("po_draft", "challan", "purchase"):
        assert "boqpick" in imports_of(mod), f"{mod}.py no longer uses the leaf"
    # And the leaf still knows about none of them.
    for mod in ("po_draft", "challan", "purchase"):
        assert mod not in imports_of("boqpick")


def test_the_balance_arithmetic_lives_upstream_in_ra():
    """
    Where the functions live is the thing that makes the import direction
    possible, so it is asserted rather than left to convention. Moving any of
    these into receipt.py forces `ra -> receipt` and the cycle with it.
    """
    import ra

    for name in ("receipts_for", "received_against", "outstanding_of",
                 "previous_balance", "prev_balance_drift"):
        assert hasattr(ra, name), f"ra.{name}() moved — the import direction depends on it"
