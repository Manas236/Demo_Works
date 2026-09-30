"""
Statutory copies on the printed documents — CLIENT_CHANGES.md §0, thirty-sixth
block, item A (30 September 2026).

The delivery challan prints Rule 55's three copies and every sheet headed TAX
INVOICE — the tax invoice, the RA bill and the merged RA document — prints
Rule 48's three. One Ctrl+P prints the set; `?copy=` reprints one lost copy.

What this file holds, each one because it is a way the feature could be wrong
while still looking finished:

* **the count and the order** — every copy of the set, in the set's order,
  on the default page;
* **the selection** — `?copy=original|duplicate|triplicate` renders exactly
  that one, and `all`, absent or anything else renders the set;
* **the overprint is on EVERY copy** — a cancelled or draft document marked on
  its first copy only would put two clean-looking copies on somebody's desk;
* **the label is never stored** — printing writes nothing to any record;
* **copies are the same document** — copies 2..N are copy 1 byte for byte,
  apart from the label;
* **only the print routes carry copies** — the `/view` pages and the five
  documents with no copy set (proforma, PO, draft PO, BOQ, measurement) are
  untouched;
* **the toolbar never prints**.
"""

import copy
import json
import re

import pytest

import docsheet as DS
from store import STORE
from test_print_golden import (  # noqa: F401  (fixtures)
    pinned_identity, golden, golden_ra, golden_dc, golden_ms, golden_dpo,
    golden_merged, GOLD_TI, GOLD_PI, GOLD_PO, GOLD_DC, GOLD_MS, GOLD_DPO,
    GOLD_MERGED)

TI_SET = DS.COPIES_TAX_INVOICE
DC_SET = DS.COPIES_DC

# (name, print URL, the copy set it must carry, the collection, the record id)
COPY_DOCS = [
    ("tax invoice",  f"/invoice/view/{GOLD_TI}",   TI_SET, "invoices",           GOLD_TI),
    ("RA bill",      "/ra/print/gold-ra",          TI_SET, "ra_bills",           "gold-ra"),
    ("merged RA",    f"/merged/print/{GOLD_MERGED}", TI_SET, "merged_ras",       GOLD_MERGED),
    ("challan",      f"/dc/print/{GOLD_DC}",       DC_SET, "delivery_challans",  GOLD_DC),
]

SHEET = re.compile(r'<div class="copy-sheet" data-copy="([a-z0-9-]+)">')
LABEL = re.compile(r'<span class="copy-lbl">([^<]*)</span>')


@pytest.fixture()
def world(client, golden, golden_ra, golden_dc, golden_dpo, golden_merged,
          golden_ms):
    """Every golden document, held still."""
    yield


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def _copies(html):
    """Each copy's markup, in page order, from its wrapper to the next one."""
    starts = [m.start() for m in SHEET.finditer(html)]
    return [html[a:b] for a, b in zip(starts, starts[1:] + [len(html)])]


# ── The sets themselves ─────────────────────────────────────────────────────

def test_the_copy_sets_are_the_statutory_strings():
    """One tuple per kind of document — the line a CA edits."""
    assert DS.COPIES_DC == ("ORIGINAL FOR CONSIGNEE",
                            "DUPLICATE FOR TRANSPORTER",
                            "TRIPLICATE FOR CONSIGNER")
    assert DS.COPIES_TAX_INVOICE == ("ORIGINAL FOR RECIPIENT",
                                     "DUPLICATE FOR TRANSPORTER",
                                     "TRIPLICATE FOR SUPPLIER")


# ── Count and order ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,url,labels,_c,_i", COPY_DOCS)
def test_the_default_page_prints_every_copy_in_order(
        name, url, labels, _c, _i, client, world):
    html = _get(client, url)
    assert SHEET.findall(html) == ["original", "duplicate", "triplicate"], (
        f"{name}: the default print is not the whole set")
    assert LABEL.findall(html) == list(labels), (
        f"{name}: the labels are not the set, in its order")


@pytest.mark.parametrize("name,url,labels,_c,_i", COPY_DOCS)
def test_every_copy_after_the_first_starts_a_new_printed_page(
        name, url, labels, _c, _i, client, world):
    html = _get(client, url)
    assert DS.COPY_STYLES in html, f"{name}: the copy stylesheet is not loaded"
    assert ".copy-sheet + .copy-sheet { break-before:page; page-break-before:always; }" \
        in DS.COPY_CSS


# ── ?copy= ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,url,labels,_c,_i", COPY_DOCS)
@pytest.mark.parametrize("pick,index", [("original", 0), ("duplicate", 1),
                                        ("triplicate", 2), ("TRIPLICATE", 2)])
def test_copy_selects_that_one_copy_alone(
        name, url, labels, _c, _i, pick, index, client, world):
    html = _get(client, f"{url}?copy={pick}")
    assert len(SHEET.findall(html)) == 1, f"{name} ?copy={pick} printed more than one"
    assert LABEL.findall(html) == [labels[index]]


@pytest.mark.parametrize("name,url,labels,_c,_i", COPY_DOCS)
@pytest.mark.parametrize("pick", ["all", "", "quadruplicate", "0", "original;x"])
def test_all_absent_or_anything_else_prints_the_set(
        name, url, labels, _c, _i, pick, client, world):
    html = _get(client, f"{url}?copy={pick}")
    assert LABEL.findall(html) == list(labels), (
        f"{name} ?copy={pick!r} did not print the whole set")


def test_copy_choice_reads_the_set_it_is_given():
    """A set a CA lengthens keeps its extra copies, keyed `copy-4` onward."""
    four = TI_SET + ("EXTRA COPY",)
    assert DS.copy_keys(four) == ("original", "duplicate", "triplicate", "copy-4")
    assert DS.copy_choice("copy-4", four) == "copy-4"
    assert DS.copy_choice("copy-4", TI_SET) == DS.COPY_ALL
    html = DS.copies(lambda lbl: f"<p>{lbl}</p>", four)
    assert html.count('class="copy-sheet"') == 4 and "EXTRA COPY" in html


# ── The overprint is on EVERY copy ──────────────────────────────────────────

def test_a_cancelled_tax_invoice_is_marked_on_every_copy(client, world):
    STORE["invoices"][GOLD_TI]["status"] = "cancelled"
    parts = _copies(_get(client, f"/invoice/view/{GOLD_TI}"))
    assert len(parts) == 3
    for p in parts:
        assert '<div class="lc-mark lc-cancelled">CANCELLED</div>' in p
        assert '<div class="lc-band lc-cancelled">' in p


@pytest.mark.parametrize("status,mark", [("cancelled", "CANCELLED"),
                                         ("draft", "DRAFT")])
def test_a_cancelled_or_draft_ra_bill_is_marked_on_every_copy(
        status, mark, client, world):
    STORE["ra_bills"]["gold-ra"]["status"] = status
    parts = _copies(_get(client, "/ra/print/gold-ra"))
    assert len(parts) == 3
    for p in parts:
        assert f'<div class="lc-mark lc-{status}">{mark}</div>' in p
        assert f'<div class="lc-band lc-{status}">' in p


def test_a_cancelled_merged_document_is_marked_on_every_copy(client, world):
    STORE["merged_ras"][GOLD_MERGED]["status"] = "cancelled"
    parts = _copies(_get(client, f"/merged/print/{GOLD_MERGED}"))
    assert len(parts) == 3
    for p in parts:
        assert '<div class="draft-mark">CANCELLED' in p


def test_each_copy_is_the_watermark_s_positioning_frame():
    """
    `.lc-mark` is absolutely positioned. With no positioned ancestor the tax
    invoice's three watermarks all landed on the first copy (measured in a
    headless print of the old code); every copy must be its own frame.
    """
    assert ".copy-sheet { position:relative; }" in DS.COPY_CSS


# ── Copies are the same document ────────────────────────────────────────────

@pytest.mark.parametrize("name,url,labels,_c,_i", COPY_DOCS)
def test_copies_differ_from_copy_one_only_in_the_label(
        name, url, labels, _c, _i, client, world):
    parts = _copies(_get(client, url))
    assert len(parts) == 3
    s1, s2, s3 = (LABEL.sub("", SHEET.sub("", p)) for p in parts)
    # Copies 1 and 2 each run from their wrapper to the next one, so they are
    # the same span; copy 3 runs on to the end of the page, so it STARTS with it.
    assert s2 == s1, f"{name}: copy 2 differs from copy 1 in more than its label"
    assert s3.startswith(s1.rstrip("\n")), (
        f"{name}: copy 3 differs from copy 1 in more than its label")
    assert len(s1) > 2000, f"{name}: the copies are suspiciously empty"


# ── The label is never stored ───────────────────────────────────────────────

@pytest.mark.parametrize("name,url,labels,coll,rid", COPY_DOCS)
def test_printing_the_set_writes_nothing_to_the_record(
        name, url, labels, coll, rid, client, world):
    before = copy.deepcopy(STORE[coll][rid])
    _get(client, url)
    for pick in ("original", "duplicate", "triplicate", "all"):
        _get(client, f"{url}?copy={pick}")
    assert STORE[coll][rid] == before, f"{name}: printing changed the record"
    stored = json.dumps(STORE[coll], default=str)
    for label in labels:
        assert label not in stored, f"{name}: {label!r} reached the store"
    assert "copy_label" not in stored and "copy-lbl" not in stored


# ── Only the print routes carry copies ──────────────────────────────────────

@pytest.mark.parametrize("url", [
    f"/dc/view/{GOLD_DC}", "/ra/view/gold-ra", f"/merged/view/{GOLD_MERGED}",
    f"/measurement/view/{GOLD_MS}"])
def test_a_view_page_shows_the_document_once_with_no_label(url, client, world):
    html = _get(client, url)
    assert 'class="copy-sheet"' not in html and 'class="copy-lbl"' not in html
    for label in TI_SET + DC_SET:
        assert label not in html, f"{url} shows a copy label"


@pytest.mark.parametrize("url", [
    f"/proforma/view/{GOLD_PI}", f"/purchase/view/{GOLD_PO}",
    f"/po/print/{GOLD_DPO}", "/boq/print/gold-boq",
    f"/measurement/print/{GOLD_MS}"])
def test_documents_with_no_copy_set_are_untouched(url, client, world):
    html = _get(client, url)
    assert 'class="copy-sheet"' not in html and 'class="copy-lbl"' not in html
    assert "copy-switch" not in html
    for label in TI_SET + DC_SET:
        assert label not in html


# ── The toolbar ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,url,labels,_c,_i", COPY_DOCS)
def test_the_toolbar_offers_four_choices_and_never_prints(
        name, url, labels, _c, _i, client, world):
    html = _get(client, url)
    bar = re.search(r'<div class="copy-switch no-print">.*?</div>', html, re.S)
    assert bar, f"{name}: no copy switch"
    hrefs = re.findall(r'href="([^"]+)"', bar.group(0))
    assert [h.split("copy=")[1] for h in hrefs] == [
        "original", "duplicate", "triplicate", "all"]
    assert '<a class="on" href="' in bar.group(0) and 'copy=all">All 3' in bar.group(0)
    assert "@media print { .copy-switch { display:none !important; } }" in DS.COPY_CSS


# ── The helpers emit the old bytes when there is no label ───────────────────

def test_no_label_emits_exactly_what_the_documents_wrote_before():
    assert DS.doc_title("TAX INVOICE") == '<div class="doc-title">TAX INVOICE</div>'
    assert DS.sheet_open(title_band="DELIVERY CHALLAN").startswith(
        '  <table class="page-frame">\n'
        '  <caption class="sheet-band">DELIVERY CHALLAN</caption>\n')
    assert DS.sheet_open(title_band="X", copy_label=None) == \
        DS.sheet_open(title_band="X")
