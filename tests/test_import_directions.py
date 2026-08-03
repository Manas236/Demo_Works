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
    ("boq", "invoice",  "any", "the RA bill is the tax invoice, not the BOQ — ra.py imports invoice, boq does not"),
    ("boq", "purchase", "any", "a BOQ does not link to a purchase order"),
    ("boq", "settings", "any", "settings imports quotation; nothing downstream of it may import back"),
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
    ("boq", "product",   "the spec picker"),
    ("boq", "store",     "the shared STORE dict"),
    ("boq", "branding",  "every company string, colour and image"),
]


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
