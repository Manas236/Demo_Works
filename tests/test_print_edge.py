"""
No browser header or footer on a printed document (26 October 2026) —
CLIENT_CHANGES.md §0, the fifty-third block, change 3.

Chrome and Edge print the date and time, the page title, the URL and "1/3" in
the page MARGIN. `docsheet.PRINT_EDGE_CSS` sets `@page { margin:0 }` so there
is no margin to print them in, and puts a 10 mm margin back inside the page —
on the body (left, right) and on the `.page-frame`'s repeating `<thead>` /
`<tfoot>` cells (top, bottom), the mechanism that already repeats the
letterhead on every page.

What this file can and cannot prove. It pins the CSS every print route ends
up with: the effective `@page` margin is 0 on every one, each keeps its own
size and orientation, the edge sheet is the LAST word on the margin, a title
band takes the top margin itself, and no register page is affected. It does
NOT drive a browser — the suite runs on boxes with none. The browser half was
MEASURED on 26 October 2026 in headless Chrome 155.0.8059.85 and Edge
143.0.3650.96 with headers and footers left ON: 23 documents and multi-page
variants, portrait and landscape — no date, time, `file://` path, title or
page counter in any PDF's text, and nothing within 5 mm of any page edge
(9.9 mm the closest). The same check on the old CSS found all five on every
document. ABOUT.md §2d and §7 gap 82 record it.
"""

import re

import pytest

import docsheet as DS
from test_print_golden import (  # noqa: F401
    GOLD_DC, GOLD_DPO, GOLD_MERGED, GOLD_MS, GOLD_MS_LEGACY, GOLD_PI, GOLD_PO, GOLD_Q,
    GOLD_TI, golden, golden_dc, golden_dpo, golden_merged, golden_ms, golden_ms_legacy,
    golden_ra, pinned_identity)
from test_work_orders import GOLD_WO, golden_wo  # noqa: F401

# Every route that prints a document, and the paper it asks for.
PRINT_ROUTES = [
    ("tax invoice",          f"/invoice/view/{GOLD_TI}",         "portrait"),
    ("proforma",             f"/proforma/view/{GOLD_PI}",        "portrait"),
    ("quotation",            f"/quotation/view/{GOLD_Q}",        "portrait"),
    ("purchase order",       f"/purchase/view/{GOLD_PO}",        "portrait"),
    ("draft PO (print)",     f"/po/print/{GOLD_DPO}",            "portrait"),
    ("draft PO (view)",      f"/po/view/{GOLD_DPO}",             "portrait"),
    ("work order (print)",   f"/wo/print/{GOLD_WO}",             "portrait"),
    ("work order (view)",    f"/wo/view/{GOLD_WO}",              "portrait"),
    ("challan (print)",      f"/dc/print/{GOLD_DC}",             "portrait"),
    ("challan (view)",       f"/dc/view/{GOLD_DC}",              "portrait"),
    ("RA tax invoice",       "/ra/print/gold-ra",                "portrait"),
    ("merged RA",            f"/merged/print/{GOLD_MERGED}",     "portrait"),
    ("joint measurement",    f"/measurement/print/{GOLD_MS}",    "landscape"),
    ("joint (view)",         f"/measurement/view/{GOLD_MS}",     "landscape"),
    ("measurement (legacy)", f"/measurement/print/{GOLD_MS_LEGACY}", "portrait"),
    ("BOQ (print)",          "/boq/print/gold-boq",              "landscape"),
    ("BOQ (view)",           "/boq/view/gold-boq",               "landscape"),
]
IDS = [r[0] for r in PRINT_ROUTES]

_PAGE_RULE = re.compile(r"@page\s*\{([^{}]*)\}")


def _styles(html: str) -> str:
    """Every <style> element's text, in document order — scripts excluded."""
    return "\n".join(re.findall(r"<style>(.*?)</style>", html, re.S))


def _effective(html: str, prop: str) -> str:
    """The value the LAST `@page` rule declaring `prop` gives it."""
    last = ""
    for body in _PAGE_RULE.findall(_styles(html)):
        m = re.search(rf"\b{prop}\s*:\s*([^;]+)", body)
        if m:
            last = m.group(1).strip()
    return last


@pytest.fixture()
def every_doc(golden, golden_ra, golden_dc, golden_dpo, golden_merged, golden_ms,
              golden_ms_legacy, golden_wo):
    yield


@pytest.mark.parametrize("name,url,paper", PRINT_ROUTES, ids=IDS)
def test_every_print_route_prints_with_no_page_margin_on_its_own_paper(
        client, every_doc, name, url, paper):
    r = client.get(url)
    assert r.status_code == 200, name
    html = r.get_data(as_text=True)
    assert DS.PRINT_EDGE_STYLES in html, f"{name} does not load the page edge"
    assert _effective(html, "margin") == "0", (
        f"{name}: a later @page rule gives the margin back — the browser would "
        f"print its header and footer in it")
    assert _effective(html, "size") == f"A4 {paper}", f"{name}: the paper changed"


@pytest.mark.parametrize("name,url,paper", PRINT_ROUTES, ids=IDS)
def test_the_margin_is_put_back_inside_the_page(client, every_doc, name, url, paper):
    css = _styles(client.get(url).get_data(as_text=True))
    assert ".page-frame > thead > tr > td { padding-top:10mm; }" in css
    assert ".page-frame > tfoot > tr > td { padding-bottom:10mm; }" in css
    assert "html body { padding:0 10mm !important; }" in css
    # Nothing after the edge sheet sets the frame cells' padding back.
    tail = css[css.index("@page { margin:0; }"):]
    assert "padding:0; border:none; background:none;" not in tail


def test_a_title_band_out_ranks_the_band_sheet_spliced_after_it():
    """
    `BAND_CSS` (`.quotation-doc .page-frame > caption`) sets `padding` and is
    spliced in AFTER `SHEET_STYLES` — at equal specificity it zeroed the top
    and the band printed 1 mm from the edge, measured. One class more wins.
    """
    assert ".quotation-doc .page-frame > caption {" in DS.BAND_CSS
    assert ".quotation-doc .page-frame > caption.sheet-band {" in DS.PRINT_EDGE_CSS
    assert 'caption class="sheet-band' in DS.sheet_open(title_band="X")


def test_the_edge_sets_the_margin_and_never_the_paper():
    rules = _PAGE_RULE.findall(DS.PRINT_EDGE_CSS)
    assert rules == [" margin:0; "]
    assert "@page { size:A4 landscape; margin:0; }" in DS.LANDSCAPE_CSS
    assert DS.SHEET_STYLES.endswith(DS.PRINT_EDGE_STYLES)


def test_no_css_page_numbers_were_shipped():
    """
    ABOUT.md §7 gap 82. A page counter needs a margin box, a margin box needs a
    non-zero @page margin, and the counter runs on across a statutory copy set.
    If one is ever added, that gap is the decision to revisit first.
    """
    for css in (DS.PRINT_EDGE_CSS, DS.LANDSCAPE_CSS):
        assert "counter(page" not in css and "@bottom-" not in css and "@top-" not in css


@pytest.mark.parametrize("url", ["/invoice/", "/purchase/", "/proforma/", "/quotation/",
                                 "/dc/", "/boq/", "/po/", "/settings/"])
def test_no_screen_page_loses_its_print_margin(client, url):
    """Only documents carry the edge: a register printed from the browser is untouched."""
    html = client.get(url).get_data(as_text=True)
    assert DS.PRINT_EDGE_STYLES not in html
    assert "@page { margin:0; }" not in html
