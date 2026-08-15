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
    ("proforma",  "invoice",   "any", "same rule, one link further down"),
    ("purchase",  "proforma",  "any", "the buy side must never touch a sell-side money document"),
    ("purchase",  "invoice",   "any", "a PO records input tax; an invoice records output tax"),
    ("proforma",  "purchase",  "any", "and the sell side must never reach across either"),
    ("invoice",   "purchase",  "any", "same"),

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
    ("po_draft", "purchase", "any", "the buy side PO is a separate pipeline entirely from Draft POs"),
    ("po_draft", "ra",       "any", "Draft POs do not need to know about Running Account bills"),
    ("po_draft", "invoice",  "any", "Draft POs have no tax block and no relation to tax invoices"),
    ("po_draft", "proforma", "any", "Draft POs have no relation to proformas"),

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
