"""
The printed documents — and one form — pinned byte-for-byte.

This file exists for one job: to prove that extracting a shared layer changed
**nothing visible** on the pages that already existed and must not move. It has
done that twice now, and each time the baseline was written and committed
BEFORE the extraction it measures, so it is a real observation rather than a
description of the result:

* `docsheet.py` — the printed A4 sheet, lifted out of four documents. The tax
  invoice, the proforma and the purchase order are pinned against it.
* `boqpick.py` — the BOQ line picker, lifted out of `po_draft.py` at its second
  consumer. `/po/create` is pinned against that one.

### What it asserts

Each document is rendered from a **fixed** record — fixed ids, fixed dates,
fixed figures — and the exact response bytes are hashed. A sha256 over the
whole page is a byte comparison: nothing about the page can move without the
digest moving. `db.py` makes the same argument for the same reason (§4,
`_digests`): a hash answers "did this change?" exactly as well as a second copy
of the thing, and a collision is not a risk worth a faster algorithm.

A whole-page digest alone would report *that* the page changed and nothing
else, which is useless when the change is meant to be nil. So each A4 document
is also split on its structural markers and each block hashed separately. A
failure then names **which block moved** — the letterhead, the party block, the
items table, the signature — which is exactly what the extraction needed to be
able to report.

### Re-deriving these numbers

They are deliberately literals, not computed. Regenerating them from the code
under test would make the file assert that the code equals itself.

When a change *is* intended — Step 3 rewrites `/ra/print` on purpose — run the
suite, read the actual digest out of the failure message, and paste it in **in
the same commit as the change**, saying in the commit body what visibly moved.
Never update one of these to make a red suite green without knowing why it
moved.
"""

import hashlib
from datetime import date as _real_date

import pytest

import branding as B
import settings as settings_mod
from store import STORE


# ── The fixed records ──────────────────────────────────────────────────────
#
# Built as dicts rather than posted through the create forms, and that is the
# point: a golden driven through `/invoice/from/<pid>` would move whenever the
# form moved, and would carry a `uuid4()` into every `url_for` on the page. A
# document whose own id is random cannot be hashed.

GOLD_Q = "gold-quotation-0001"
GOLD_PI = "gold-proforma-0001"
GOLD_TI = "gold-invoice-0001"
GOLD_PO = "gold-purchase-0001"


def _line_items():
    return [
        {"type": "assembly", "name": "Fire pump set, 2280 LPM", "part_no": "FPS-2280",
         "hsn": "84131990", "qty": 2.0, "unit": "Nos", "price": 185000.0,
         "total": 370000.0, "depth": 0},
        {"type": "item", "name": "Pressure switch", "part_no": "PS-10",
         "hsn": "85365090", "qty": 2.0, "unit": "Nos", "price": 0.0,
         "total": 0.0, "depth": 1},
        {"type": "item", "name": "MS heavy duty 'C' class pipe, 150 mm dia",
         "part_no": "PIPE-150", "hsn": "", "qty": 120.0, "unit": "Mtrs",
         "price": 2024.0, "total": 242880.0, "depth": 0},
    ]


TAX_INFO = {"CGST": 55159.20, "SGST": 55159.20, "total": 110318.40,
            "cgst_rate": 9.0, "sgst_rate": 9.0}


@pytest.fixture()
def pinned_identity():
    """
    The specimen company identity, forced on and put back afterwards.

    The letterhead, the foot strip, the signature block and the bank block are
    all read from `branding` at render time, and `branding` is a module global
    that `/settings` rewrites. `ensure_demo_settings()` is **not** enough on its
    own: it is guarded by an unpersisted seed flag and only ever fills a gap, so
    once any earlier test has posted a company field the seeder is a no-op and
    the golden hashes somebody else's letterhead.

    That is not hypothetical — it is what these three assertions did on the
    first full-suite run: green alone, red in the suite, with exactly the four
    identity-bearing blocks moved and the document body untouched.
    """
    saved = STORE["settings"].get(settings_mod.RECORD_ID)
    STORE["settings"][settings_mod.RECORD_ID] = dict(settings_mod.DEMO_COMPANY)
    B.apply_settings(settings_mod.load_saved())
    yield
    if saved is None:
        STORE["settings"].pop(settings_mod.RECORD_ID, None)
    else:
        STORE["settings"][settings_mod.RECORD_ID] = saved
    B.apply_settings(settings_mod.load_saved())


@pytest.fixture()
def golden(client, pinned_identity):
    """One store holding exactly the three documents this file hashes."""
    STORE["quotations"][GOLD_Q] = {
        "id": GOLD_Q, "ref": "QT-0001", "date": "2026-04-10",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": "Prudent Teqtis Pvt Ltd\nMr R Nair\nSurvey 21, Whitefield\nBangalore, Karnataka - 560066",
        "bill_gstin": "29AABCP1234C1ZX", "bill_state": "Karnataka",
        "ship_same": "on", "line_items": _line_items(),
        "subtotal": 612880.0, "tax_type": "cgst_sgst", "tax_info": TAX_INFO,
        "grand_total": 723198.40, "total_qty": 122.0,
    }

    STORE["proformas"][GOLD_PI] = {
        "id": GOLD_PI, "ref": "PI-0001", "date": "2026-04-12",
        "quotation_id": GOLD_Q, "quotation_ref": "QT-0001",
        "quotation_date": "2026-04-10",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": STORE["quotations"][GOLD_Q]["to"],
        "bill_gstin": "29AABCP1234C1ZX", "ship_same": "on",
        "line_items": [dict(r) for r in _line_items()],
        "subtotal": 612880.0, "tax_type": "cgst_sgst", "tax_info": TAX_INFO,
        "grand_total": 723198.40, "total_qty": 122.0,
        "po_number": "PT/PO/2026/117", "po_date": "2026-04-11",
        "advance_pct": 100.0, "amount_due": 723198.40, "balance_due": 0.0,
        "prior_invoiced": 0.0, "prior_refs": [],
        "payment_terms": "30 days from invoice", "delivery_terms": "Ex-works",
        "delivery_date": "2026-05-15", "dispatch_through": "By Road Transport",
        "incoterms": "", "validity_days": "15", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }

    STORE["invoices"][GOLD_TI] = {
        "id": GOLD_TI, "ref": "SF/TI/26-27/0001", "fy": "26-27",
        "date": "2026-05-20",
        "proforma_id": GOLD_PI, "proforma_ref": "PI-0001",
        "proforma_date": "2026-04-12",
        "quotation_id": GOLD_Q, "quotation_ref": "QT-0001",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": STORE["quotations"][GOLD_Q]["to"],
        "bill_gstin": "29AABCP1234C1ZX", "ship_same": "",
        "ship_acct_name": "Prudent Teqtis — Site Store",
        "ship_addr": "Gate 3, Whitefield Campus", "ship_city": "Bangalore",
        "ship_state": "Karnataka", "ship_pin": "560066",
        "ship_phone": "", "ship_gstin": "",
        "line_items": [dict(r) for r in _line_items()],
        "subtotal": 612880.0, "tax_type": "cgst_sgst", "tax_info": TAX_INFO,
        "grand_total": 723198.40, "total_qty": 122.0,
        "place_of_supply": "Karnataka", "pos_code": "29",
        "reverse_charge": False,
        "advance_received": 200000.0, "net_payable": 523198.40,
        "po_number": "PT/PO/2026/117", "po_date": "2026-04-11",
        "dispatch_through": "By Road Transport", "dispatch_doc_no": "BLR/4471",
        "vehicle_no": "KA05 AB 1234", "eway_bill_no": "391004471123",
        "payment_terms": "30 days from invoice",
        "notes": "Balance payable within 30 days.",
        "company_branch": "", "auth_signatory": "",
        # APPROVED — CC-2 B7. See the note on the RA golden below: an
        # approved document emits no print-blanking block, so this sheet
        # is byte-identical to what it was before B6 and B7 existed.
        "approval_status": "approved",
    }

    STORE["purchases"][GOLD_PO] = {
        "id": GOLD_PO, "ref": "SF/PO/26-27/0001", "fy": "26-27",
        "date": "2026-04-18",
        "vendor_id": "", "vendor_name": "Vishwakarma Pumps & Motors Pvt. Ltd.",
        "vendor_gstin": "33AACCV5678D1Z2",
        "to": ("Vishwakarma Pumps & Motors Pvt. Ltd.\nKind Attn: Mr S Ramanathan\n"
               "Plot 44, SIDCO Industrial Estate\nCoimbatore, Tamil Nadu - 641021"),
        "vendor_ref": "VPM/Q/2026/88",
        "quotation_id": GOLD_Q, "quotation_ref": "QT-0001",
        "line_items": [
            {"type": "item", "name": "Fire pump set, 2280 LPM", "part_no": "FPS-2280",
             "hsn": "84131990", "qty": 2.0, "unit": "Nos", "price": 128000.0,
             "total": 256000.0, "depth": 0},
            {"type": "item", "name": "Pressure switch", "part_no": "PS-10",
             "hsn": "", "qty": 4.0, "unit": "Nos", "price": 1150.0,
             "total": 4600.0, "depth": 0},
        ],
        "subtotal": 260600.0, "tax_type": "cgst_sgst",
        "tax_info": {"CGST": 23454.0, "SGST": 23454.0, "total": 46908.0,
                     "cgst_rate": 9.0, "sgst_rate": 9.0},
        "grand_total": 307508.0, "total_qty": 6.0,
        "delivery_date": "2026-05-02",
        "delivery_to": "Samruddhi Fire Services — Whitefield site store",
        "payment_terms": "30 days from invoice", "delivery_terms": "Ex-works",
        "dispatch_through": "By Road Transport", "incoterms": "",
        "status": "Issued",
        "status_history": [{"at": "2026-04-18 09:00", "status": "Issued",
                            "note": "Raised against QT-0001."}],
        "notes": "Please confirm despatch date by return.",
        "company_branch": "", "auth_signatory": "",
        # APPROVED — CC-2 B7. See the note on the RA golden below: an
        # approved document emits no print-blanking block, so this sheet
        # is byte-identical to what it was before B6 and B7 existed.
        "approval_status": "approved",
    }

    yield

    STORE["quotations"].pop(GOLD_Q, None)
    STORE["proformas"].pop(GOLD_PI, None)
    STORE["invoices"].pop(GOLD_TI, None)
    STORE["purchases"].pop(GOLD_PO, None)


@pytest.fixture()
def golden_ra(client, pinned_identity):
    """
    One issued RA bill, fixed end to end.

    Built directly rather than through `/ra/create` for the same reason as the
    three above, plus one of its own: the entry form assigns `ra_no` and mints
    an id server-side, and neither is a thing a golden can hold still.
    """
    import ra

    STORE["boqs"].clear()
    STORE["ra_bills"].clear()

    spec_line = {
        "line_id": "aaaaaaaaaaaa", "item_no": "24", "parent_item_no": "",
        "section": "B", "is_header": True,
        "description": ("Providing and fixing MS heavy duty 'C' class pipe "
                        "conforming to IS 1239 / IS 3589, including all "
                        "fittings, supports and testing."),
        "remark": "", "unit": "", "area_qty": {}, "total_qty": 0.0,
        "supply_base_rate": None, "supply_escalation_pct": 0.0,
        "supply_rate": 0.0, "supply_amount": 0.0,
        "supply_hsn": "", "supply_gst_rate": 18.0,
        "install_base_rate": None, "install_escalation_pct": 0.0,
        "install_rate": 0.0, "install_amount": 0.0,
        "install_sac": "", "install_gst_rate": 18.0,
    }
    child = dict(spec_line, line_id="bbbbbbbbbbbb", item_no="24.b",
                 parent_item_no="24", is_header=False,
                 description="150 mm dia", unit="Mtrs",
                 area_qty={"T1": 700.0}, total_qty=700.0,
                 supply_base_rate=1760.0, supply_escalation_pct=15.0,
                 supply_rate=2024.0, supply_amount=1416800.0,
                 supply_hsn="73063090", supply_gst_rate=18.0)

    STORE["boqs"]["gold-boq"] = {
        "id": "gold-boq", "ref": "SF/BOQ/26-27/0001", "fy": "26-27",
        "date": "2026-04-01", "rev_no": 0, "supersedes": "",
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": "Prudent Teqtis Pvt Ltd\nSurvey 21, Whitefield\nBangalore, Karnataka - 560066",
        "bill_gstin": "29AABCP1234C1ZX", "ship_same": "on",
        "rate_basis_label": "Mohali Rates",
        "sections": [{"code": "B", "title": "Hydrant system", "areas": ["T1"]}],
        "line_items": [spec_line, child],
        "supply_subtotal": 1416800.0, "install_subtotal": 0.0,
        "subtotal": 1416800.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }

    c = ra.build_claim(child, 80.0, 2024.0, 120.0, 2024.0)
    subtotal, drows, dtotal, net = ra.bill_totals([c], [])
    tax = ra.compute_tax_totals([c], [], "cgst_sgst", 9.0, 9.0, 18.0)

    bill = {
        "id": "gold-ra", "ref": "SF/RA/26-27/0002", "fy": "26-27",
        "date": "2026-06-05",
        "tax_invoice_ref": "SF-3", "tax_invoice_date": "2026-06-05",
        "po_ref": "PT/WO/2026/44", "po_date": "2026-03-28",
        "boq_id": "gold-boq", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "ra_no": 2, "leg": "supply",
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": STORE["boqs"]["gold-boq"]["to"],
        "bill_gstin": "29AABCP1234C1ZX",
        "claims": [c], "claim_subtotal": subtotal,
        "deductions": drows, "deduction_total": dtotal, "net_payable": net,
        "prev_balance": 250000.0, "prev_balance_refs": ["SF/RA/26-27/0001"],
        "status": "issued", "issued_on": "2026-06-05",
        "cancelled_on": "", "cancel_reason": "",
        "notes": "", "company_branch": "", "auth_signatory": "",
        # ⚠ **APPROVED — CC-2 B7, 29 August 2026, and this is what keeps the
        #   goldens byte-identical.** B7 refuses to print a document that has
        #   not completed its approval ladder, and `/invoice/view` and
        #   `/purchase/view` carry a print-blanking stylesheet when it has not.
        #   An APPROVED document emits neither — `approval.print_block()`
        #   returns the empty string — so the sheet below is exactly the page it
        #   was before B6 and B7 existed, and every digest in this file was
        #   re-measured unchanged rather than re-baselined.
        #
        #   That is also the honest thing for these fixtures to say. After B7 a
        #   printable document IS an approved one, so a golden pinning "the
        #   printed sheet" is pinning an approved document's sheet. The refusal
        #   path has its own tests in `tests/test_approval_b7.py`.
        "approval_status": "approved",
    }
    bill.update(tax)
    STORE["ra_bills"]["gold-ra"] = bill

    yield

    STORE["boqs"].clear()
    STORE["ra_bills"].clear()


# ── Hashing ────────────────────────────────────────────────────────────────

# Ordered structural markers of the shared A4 sheet. Each block runs from its
# own marker to the next one, so a change confined to one block moves exactly
# one digest and the failure message names it.
SHEET_BLOCKS = [
    ("head",       "<head>"),
    ("letterhead", "<thead><tr><td>"),
    ("foot-strip", "<tfoot><tr><td>"),
    ("doc-box",    '<div class="doc-box">'),
    # The class attribute is matched WITHOUT its closing quote, because the
    # delivery challan's party block carries a second class
    # (`doc-header dc-2col`) and would otherwise carry no marker at all. The
    # four sheets that carry the bare class find the identical offset either
    # way, so their digests are untouched — which the four assertions below
    # are what proves.
    ("party",      '<div class="doc-header'),
    ("items",      '<div class="items-wrap">'),
    ("signature",  '<div class="sig-block">'),
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _blocks(html: str, markers) -> dict:
    """Split on ordered markers; each block is marker[i] .. marker[i+1]."""
    cuts, missing = [], []
    for name, marker in markers:
        at = html.find(marker)
        if at < 0:
            missing.append(f"{name} ({marker!r})")
        cuts.append((name, at))
    assert not missing, (
        f"the document no longer carries these structural markers: {missing}. "
        f"That is a layout change, not a digest drift — read what moved before "
        f"touching the expected values below.")

    out = {}
    for i, (name, at) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else len(html)
        out[name] = _sha(html[at:end])
    return out


def _check(html: str, expect_whole: str, expect_len: int, expect_blocks=None,
           markers=SHEET_BLOCKS, what: str = "document"):
    got_len, got_whole = len(html), _sha(html)
    if expect_blocks is not None and got_whole != expect_whole:
        got_blocks = _blocks(html, markers)
        moved = [n for n in expect_blocks if got_blocks[n] != expect_blocks[n]]
        assert not moved, (
            f"{what}: these blocks changed — {moved}. "
            f"Expected {expect_blocks}, got {got_blocks}. "
            f"Whole page {expect_whole} -> {got_whole}, "
            f"{expect_len} -> {got_len} bytes.")
    assert (got_whole, got_len) == (expect_whole, expect_len), (
        f"{what}: the rendered page changed. "
        f"sha {expect_whole} -> {got_whole}, bytes {expect_len} -> {got_len}. "
        f"Every structural block hashed the same, so the difference is outside "
        f"them — the screen chrome, or text between two blocks.")


# ═══ The three documents ═══════════════════════════════════════════════════

# ── Re-baselined 27 August 2026 — the unescaped-output pass ────────────────
#
# **What moved, and why re-baselining is the correct answer here.** All five
# documents moved by exactly **+8 bytes**, in exactly **two blocks** —
# `letterhead` and `foot-strip` — with `head`, `doc-box`, `party`, `items` and
# `signature` hashing identically on every one of them. Nothing about any
# document's layout, figures or wording changed.
#
# The whole of the difference is one character in one field:
#
#     branding.COMPANY_TAGLINE == "Fire Protection Systems & Services"
#
#   before  <div class="lh-tag">&#8212; Fire Protection Systems & Services &#8212;</div>
#   after   <div class="lh-tag">&#8212; Fire Protection Systems &amp; Services &#8212;</div>
#
#   before  <div class="lh-foot">SAMRUDDHI FIRE &middot; Fire Protection Systems & Services</div>
#   after   <div class="lh-foot">SAMRUDDHI FIRE &middot; Fire Protection Systems &amp; Services</div>
#
# `&` -> `&amp;` is +4 bytes, the tagline prints twice per sheet, so +8 bytes
# per document — which is the arithmetic every one of the five reported.
#
# **A browser draws both spellings as the same `&`.** The rendered documents
# are visually identical; only the bytes moved. They moved because
# `COMPANY_TAGLINE` is a `/settings` field that was previously emitted RAW —
# which is the defect this pass closed, demonstrating itself on the one default
# value that happens to contain an escapable character. `B.field()`,
# `docsheet._contact_bit()`, `letterhead()` and `foot_strip()` now escape.
#
# Every other statutory default (`27AAAAA0000A1Z5`, `AAAAA0000A`,
# `SPECIMEN BANK LTD.`, the invented address) is alphanumeric, so no other
# field moved a byte — which is why only these two blocks did.
#
# The old digests are kept in the comment above each set rather than deleted.


# Captured 15 August 2026, against the code as it stood BEFORE `docsheet.py`
# existed. These three numbers are the baseline the extraction is measured by.
# ⚠ **RE-BASELINED 29 August 2026 (third pass) for the NAVIGATION link, and
#   the movement is the intended outcome of an authorised change rather than a
#   surprise.** The employee master shipped on 29 August with no nav entry
#   precisely so that this file would not move; the owner then could not find
#   the page. `dashboard.NAV_ITEMS` gained `Employees`, and because `_nav()` is
#   embedded in every printed page **the bytes moved while the paper did not**.
#
#   Measured, per document: **+248 bytes, and the `head` block ALONE.**
#   `letterhead`, `foot-strip`, `doc-box`, `party`, `items` and `signature` are
#   byte-identical on every one of them. The 248 bytes are one `<a
#   class="nav-link">` inside `<nav>…</nav>`, which
#   `quotation.VIEW_DOC_STYLES` hides with `display:none !important` under
#   `@media print` — so **not one figure, label or visible character on any
#   printed sheet changed.** `tests/test_nav_reachability.py` asserts both
#   halves directly rather than leaving them to this comment.
#
#   ⚠ **The delivery challan did NOT move**: `challan.print_dc` renders no nav
#   at all, which ABOUT.md §7 already recorded as the shape all six should
#   have. Its digest below is untouched, and that is the measurement that says
#   the coupling is avoidable rather than inherent.
#
#   ⚠ **RE-BASELINED AGAIN 29 August 2026 (fifth pass) for the MEASUREMENT
#     register's nav entry** — CC-2 C2. `dashboard.NAV_ITEMS` gained a fourth
#     entry and it is the FIRST DOCUMENT REGISTER in that nav; `dashboard.py`
#     carries the note about what that does to the "the nav is not the launcher"
#     rule.
#
#     Measured, per document: **+342 bytes, and the `head` block ALONE**, on the
#     tax invoice, the proforma, the purchase order, the RA bill and the BOQ
#     line picker. `letterhead`, `foot-strip`, `doc-box`, `party`, `items` and
#     `signature` are byte-identical on every one of them.
#
#     **The 342 bytes are the whole of the delta and they are one anchor.**
#     `NAV_LINK_SEP` plus `<a href="/measurement/" class="nav-link">` plus the
#     `boq` icon SVG plus `Measurements</a>` measures 342 characters exactly,
#     and every page grew by exactly 342 — so the delta is the link and nothing
#     else. It sits inside `<nav>…</nav>`, which `quotation.VIEW_DOC_STYLES`
#     hides with `display:none !important` under `@media print`, so **not one
#     figure, label or visible character on any printed sheet changed.**
#     `tests/test_nav_reachability.py` asserts both halves directly and is now
#     parametrised over BOTH recorded "before" states, so the employee link's
#     confinement is still asserted rather than quietly retired.
#
#     ⚠ **The delivery challan did NOT move again**, for the same reason: it
#     renders no nav at all. Its digest below is untouched a second time.
# ⚠ **RE-BASELINED 14 September 2026 — THE NAV IS GONE FROM EVERY PRINT ROUTE,
#   and this is the LAST time a navigation change can move a printed document.**
#   ABOUT.md §7's first gap ("Global Nav vs Print Goldens") is closed by this
#   commit: `/invoice/view`, `/proforma/view`, `/purchase/view`, `/ra/print` and
#   `/merged/print` no longer call `_nav()`, which gives them the shape
#   `/dc/print`, `/boq/print` and `/po/print` always had. The re-baseline goes
#   the other way from the two before it — to a SMALLER output — and it is the
#   re-baseline that ends re-baselines: from here on, `_nav()` is not on any
#   page this file hashes except the `/po/create` picker, which is a form.
#
#   Measured, per document: **−9,297 bytes, and the `head` block ALONE.**
#
#     | document           | before  | after   | delta  | blocks moved |
#     | tax invoice        | 110,806 | 101,509 | −9,297 | head         |
#     | proforma           | 104,371 |  95,074 | −9,297 | head         |
#     | purchase order     | 107,215 |  97,918 | −9,297 | head         |
#     | RA bill            |  98,254 |  88,957 | −9,297 | head         |
#     | merged tax invoice |  96,624 |  87,327 | −9,297 | head         |
#     | delivery challan   |  83,657 |  83,657 |      0 | none         |
#     | BOQ                | 100,879 | 100,879 |      0 | none         |
#     | draft PO           |  83,807 |  83,807 |      0 | none         |
#     | /po/create picker  |  55,088 |  55,088 |      0 | none         |
#
#   The 9,297 bytes are `<nav>…</nav>` — the brand mark with its base64 logo,
#   the four filtered entries, the subtitle pill — plus the empty persistence
#   strip and the line the call sat on. `letterhead`, `foot-strip`, `doc-box`,
#   `party`, `items` and `signature` are byte-identical on every one of the
#   five, so not one figure, label or visible character on any printed sheet
#   changed; `test_no_print_route_renders_the_nav` below is what keeps it out.
#
#   ⚠ The stylesheet the sheets load (`DS.SHEET_STYLES`) still begins with
#     `BASE_STYLES`, which carries the `nav {}` rules. They are dead on these
#     pages now and are left where they are: `BASE_STYLES` is shared by every
#     page in the application and is not this commit's to edit.
GOLD_TI = "gold-ti"
# was ab555e45cd245fa5 / 110208 before the 27 Aug 2026 escaping pass
# was f91031b44e1e7dc7 / 110216 before the 29 Aug 2026 nav re-baseline
# was 92903e2e6134597b / 110464 before the 29 Aug 2026 MEASUREMENT nav entry
# was 9141446abd5ec906 / 110806 before the 14 Sep 2026 nav removal
# was ad1aa6915247c18c / 101509 before the 23 Sep 2026 cancellation overprint.
#     ⚠ **`head` ALONE moved, and every other block is byte-identical** — the
#     +1,698 bytes are the `.lc-mark` / `.lc-band` rules added to
#     INVOICE_STYLES so a cancelled tax invoice prints marked (ABOUT.md §5
#     `/invoice`). `doc-box` is unchanged because `{void_html}` carries its own
#     leading newline and renders as the empty string on an invoice that has
#     not been cancelled, which is what GOLD_TI is. The sheet a customer
#     receives did not move; only what the page is capable of drawing did.
TI_WHOLE = "5ddd3ce9c8f7b634"
TI_LEN = 103207
TI_BLOCKS = {"head":       "b5312294e91a796f",   # was 59522cc02d192043,
                                                  # was 13840b8797d6e721,
                                                  # was f76089afb5505200,
                                                  # was 49524db46e29dcc5
             "letterhead": "3c080a57f60c89e9",
             "foot-strip": "1efaaf73d3a0a076",
             "doc-box":    "5e4d6a24b0a5b726",
             "party":      "a7c0e4ecf0b1491f",
             "items":      "ace24562781a2e31",
             "signature":  "f5511fad8e1212cc"}

# was 4f7794a81d90071c / 101851 before the 27 Aug 2026 escaping pass
# Was e21237eb007ee61b / 101,859 before the 27 Aug 2026 Phase 3A pass added the
# discount column (CLIENT_CHANGES-2.md A2). **+942 bytes, in two blocks, and
# every one of them is accounted for:**
#
#   head  +721 = the `.c-disc` print rule and its comment (+634), the two
#                `grid-template-columns` rows of the form's line editor widening
#                by one 80px cell (+10), and the mobile rule that hides the new
#                box with the amount (+77). All three live in `PURCHASE_STYLES`
#                and not in `QUOTATION_STYLES`, which is why the quotation, the
#                proforma and the tax invoice below did NOT move.
#   items +221 = one `<th class="c-disc">Disc %</th>` (+41), one `c-disc` cell
#                on each of the two line rows (+84), and one empty `c-disc` cell
#                on each of the three tax summary rows and the Order Value row
#                (+96), which `DS.SUM_BLANKS` / `DS.TOTAL_BLANKS` supply.
#
# letterhead, foot-strip, doc-box, party and signature are byte-identical, and
# so is every figure on the sheet: the golden PO carries no `discount_pct`, so
# its Disc % column prints an em dash and its Order Value is unchanged at
# 307,508.00. A2 moved the shape of this document, not its arithmetic.
# Was 809c8921d502d98b / 102,801 before the 28 August 2026 pass lifted A1's
# Draft-only narrowing. **+1,021 bytes, in ONE block, and every byte of it is
# accounted for:**
#
#   head  +1021 = the `.po-reprice` / `.rp-*` rules and their comment, added to
#                 `PURCHASE_STYLES` for A1's rate-change trail (+939), and the
#                 `<a ... >Reprice</a>` anchor in the action bar (+82, of which
#                 36 are the golden order's own id in the href).
#
# **Why the anchor lands in `head`:** the `head` block runs from `<head>` to
# `<thead><tr><td>`, so it carries the stylesheet, the nav AND the screen action
# bar — everything above the letterhead. It is not only the `<head>` element.
#
# **The anchor is there because the golden order is `Issued`.** Until this pass
# `can_edit_rates()` refused every status but `Draft`, so no Reprice button was
# offered on it. The narrowing was lifted under the 28 August 2026 override
# block, which is the feature, not a regression — `test_po_rate_edit.py`'s
# `test_the_reprice_button_is_offered_on_every_live_order_...` is the assertion
# that names it.
#
# letterhead, foot-strip, doc-box, party and signature are **byte-identical**,
# and so is every figure on the sheet: the golden PO has never been repriced, so
# `_reprice_html()` returns "" and no `Rate changes` panel renders. Nothing on
# the printed document moved — `.po-panel` is `display:none` at print, and the
# only two things that did move are a stylesheet rule and a screen button.
# Moved a second time in the same 28 August 2026 pass, by A3's charge lines.
# **+937 bytes, in the SAME one block, and it is one thing:**
#
#   head  +937 = the `.chg-head` / `.chg-row` / `.chg-tax` rules and their
#                comment, added to `PURCHASE_STYLES` for the charge repeater on
#                `/purchase/create` and `/purchase/edit/<id>`.
#
# ⚠ **`items` did NOT move, and that is the property A3 was built to hold.**
#   The golden order carries no `charges`, so `charges_of()` returns `[]`, no
#   Sub Total row and no charge rows are drawn, and the Taxable Value row prints
#   `taxable_value` — which falls back to `subtotal` and is the identical
#   260,600.00 it always printed. Order Value is unchanged at 307,508.00. **Not
#   one figure on the printed sheet moved**; a stylesheet did.
#
# Moved a THIRD time on 29 August 2026, by the extra free-text purchase-order
# lines. **+1,800 characters, in the SAME one block, and it is one thing:**
#
#   head  +1,800 = the `.xl-head` / `.xl-row` / `.xl-assumed` rules and their
#                  comments, added to `PURCHASE_STYLES` for the extra-line
#                  repeater on `/purchase/create` and `/purchase/edit/<id>`.
#
# That figure was **measured, not derived**: the stylesheet block added to
# `PURCHASE_STYLES` is 1,800 characters long and the page grew by 1,800, so the
# delta is the stylesheet and nothing else — not one other character of this
# document moved.
#
# ⚠ **`items` did NOT move again, for the same reason and a second one.** The
#   golden order carries no `extra_lines`, so `extra_lines_of()` returns `[]`
#   and the loop that draws them runs zero times: no extra row, no serial
#   number consumed, nothing added to `total_qty`, and `subtotal` unchanged at
#   260,600.00 because `extra_lines_total([])` is 0.0. Order Value is still
#   307,508.00. The `job costing` chip is also unchanged — its extra-parts
#   clause renders only when there is extra-line value, exactly as
#   `reprice_btn` renders only on a live order.
#
# ⚠ **The assumed-rate chip cannot reach this document even when an order does
#   carry one.** `.xl-assumed` is `display:none` at print. That is asserted
#   directly in `tests/test_po_extra_lines.py` rather than inferred from here.
# Moved a FOURTH time on 14 September 2026, by the HSN box on the extra-parts
# repeater. **+66 bytes, in the SAME one block, and it is one thing:**
#
#   head  +66 = the `.xl-head, .xl-row` grid gaining one `100px` column, the
#               mobile rule hiding `extra_hsn` with the other narrow cells, and
#               the comment above them saying so — all in `PURCHASE_STYLES`.
#
# That figure was **measured, not derived**: `PURCHASE_STYLES` grew by 66
# characters against `HEAD` and the page grew by 66, so the delta is the
# stylesheet and nothing else.
#
# ⚠ **`items` did NOT move, for the reason it never has.** The golden order
#   carries no `extra_lines`, so no extra row is drawn and no HSN cell — full
#   or chipped — reaches this sheet. On an order that DOES carry one, the HSN
#   cell now prints what was typed, and the `add HSN` chip only where nothing
#   was; until this pass that chip was asking for a figure no form had a box
#   for, which is the defect the box closes.
# was 0b7ed84b19fa2646 / 106559 before the 29 Aug 2026 nav re-baseline
# was a7b30226a545aa62 / 106807 before the 29 Aug 2026 MEASUREMENT nav entry
# was ac40e815028168a7 / 107149 before the 14 Sep 2026 extra-parts HSN box
# was 787bf73b6440206f / 107215 before the 14 Sep 2026 nav removal
PO_WHOLE, PO_LEN = "32a83f94e0620545", 97918
PO_BLOCKS = {"head":       "bf2fc2b883a29ca6",   # was b0183c538998f277,
                                                 # was e6bade8d45a63f6a,
                                                 # was 09c8c69b2580ee92,
                                                 # was 823a24d818d5f0c3,
                                                 # was aa05dcac55729c51,
                                                 # was c4b27c10e58c1b4f,
                                                 # was 5354379fd4182ed2,
                                                 # was d0df61b20bb3a42e
             "letterhead": "2800166c693cc2f1",
             "foot-strip": "1efaaf73d3a0a076",
             "doc-box":    "ffe286e7afd8c90b",
             "party":      "307d35714073c084",
             "items":      "5e17a6d93410823c",   # was fd759d99cf4b162a
             "signature":  "5717ca48143d8b6e"}

GOLD_PI = "gold-pi"
# was 4969d5e4f6a6508b / 103773 before the 27 Aug 2026 escaping pass
# was d4fe110738e8d20f / 103781 before the 29 Aug 2026 nav re-baseline
# was 9a509c8c1f87ce5c / 104029 before the 29 Aug 2026 MEASUREMENT nav entry
# was 8cf87b4361ccc740 / 104371 before the 14 Sep 2026 nav removal
PI_WHOLE = "cdf95f1856eff934"
PI_LEN = 95074
PI_BLOCKS = {"head":       "8d0355644f96b13c",   # was fb2abee257b52d86,
                                                  # was 0250890a6d6e2f6b,
                                                  # was a3b342e73adf07fc
             "letterhead": "1c368b0c8259abe0",
             "foot-strip": "1efaaf73d3a0a076",
             "doc-box":    "77fa68a83f706064",
             "party":      "9427bbb3e9495dd8",
             "items":      "ee2126dae594bc30",
             "signature":  "964248284443ca1b"}

# Recaptured after `/ra/print` was rebuilt on the shared A4 sheet. The previous
# baseline was `88a55e81022ec48a` / 53,382 bytes — a `.doc-paper` card in Inter
# over a slate palette, with no letterhead, no page frame and money in Western
# digit grouping. See the test below for what moved.
GOLD_RA = "gold-ra"
# was 2e12fa898f1b39fe / 97656 before the 27 Aug 2026 escaping pass
# was 1c5f5c7e6720628f / 97664 before the 29 Aug 2026 nav re-baseline
# was 7f964e7dceb2699f / 97912 before the 29 Aug 2026 MEASUREMENT nav entry
# was 74982d79ad492c09 / 98254 before the 14 Sep 2026 nav removal
RA_WHOLE = "1a6acf617d3c07f8"
RA_LEN = 88957
RA_BLOCKS = {"head":       "184a84d3609eaf57",   # was 837ea9b648848976,
                                                  # was 924f39af975d8d7b,
                                                  # was ea1ccbaa59c99616
             "letterhead": "3c080a57f60c89e9",
             "foot-strip": "1efaaf73d3a0a076",
             "doc-box":    "44c7368b5a1b2380",
             "party":      "0a1ad2e74686542a",
             "items":      "92f5cc2dd233b05b",
             "signature":  "4ebebebbdf2383c8"}


def test_the_tax_invoice_document_is_unchanged(client, golden):
    """`/invoice/view/<id>` — the Rule 46 sheet. Must not move."""
    r = client.get(f"/invoice/view/{GOLD_TI}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), TI_WHOLE, TI_LEN, TI_BLOCKS,
           what="tax invoice")


def test_the_proforma_document_is_unchanged(client, golden):
    """
    `/proforma/view/<id>` — the payment-request sheet.

    Pinned for one specific reason: the **bank block** on this page is the one
    the RA bill needed, and moving it into `docsheet.py` is the only way both
    documents can carry the same one without `ra.py` importing `proforma.py`.
    A relocation that changes the page it came from is not a relocation.
    """
    r = client.get(f"/proforma/view/{GOLD_PI}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), PI_WHOLE, PI_LEN, PI_BLOCKS,
           what="proforma invoice")


def test_the_purchase_order_document_is_unchanged(client, golden):
    """`/purchase/view/<id>` — the buy-side sheet. Must not move."""
    r = client.get(f"/purchase/view/{GOLD_PO}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), PO_WHOLE, PO_LEN, PO_BLOCKS,
           what="purchase order")


def test_the_ra_bill_document_matches_its_recorded_baseline(client, golden_ra):
    """
    `/ra/print/<id>` — the RA bill tax invoice, now on the shared A4 sheet.

    This one was **expected to change** and did. What moved, against the
    53,382-byte baseline captured before the rework:

    - it gained the repeating **letterhead** and the `.page-frame` that carries
      it onto every printed page, the **foot strip**, the amber `todo-chip`
      treatment for a blank HSN/SAC, and a proper **signature block** with the
      company GSTIN and PAN;
    - the four `.box-card` panels became the sheet's three-cell **party block**,
      so the buyer sits where the buyer sits on every other document and the
      two number series read as two rows of meta rather than as prose;
    - the items table became the sheet's eight-column `.q-table`, with **Qty
      before Unit** as the other documents have it, and the totals became
      `docsheet` rows;
    - money moved from `&#8377;&nbsp;{v:,.2f}` to `_inr()` — **Indian digit
      grouping, no symbol**, which is what ABOUT.md §9 has always specified for
      a printed document and what the other four already did;
    - the bank block is the proforma's, not a second one.

    What did **not** move: every figure, every item number, every HSN/SAC and
    the whole snapshot contract. `tests/test_ra_print_immutability.py` is what
    holds that, and it still does.
    """
    r = client.get("/ra/print/gold-ra")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), RA_WHOLE, RA_LEN, RA_BLOCKS,
           what="RA bill")


def test_the_ra_bill_and_the_tax_invoice_carry_the_SAME_letterhead(
        client, golden, golden_ra):
    """
    The point of the whole exercise, asserted directly.

    Four documents used to write their own letterhead and their own foot strip.
    The client's complaint was not that any one of them was wrong — it was that
    they did not look like each other. So the assertion is not "both have a
    letterhead" but **the same bytes**, and it fails the day somebody adds a
    line to one document instead of to `docsheet.letterhead()`.

    **The RA bill and the tax invoice must match exactly**, because they are
    the same instrument: both are headed TAX INVOICE, both create a GST
    liability, and Rule 46 wants the supplier's GSTIN on the face of each.

    Two documents differ, both on purpose and both pinned here so that a change
    to either is a decision rather than a drift:

    - the **proforma** prints the branch list where these two print the GSTIN.
      A proforma is not a statutory record and says so on its own face;
    - the **purchase order** omits the web address. That one is *not*
      defensible, is not defended, and is ABOUT.md §7 gap 18.

    Every one of the four carries the same foot strip, with no exceptions.
    """
    ti = _blocks(client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True),
                 SHEET_BLOCKS)
    pi = _blocks(client.get(f"/proforma/view/{GOLD_PI}").get_data(as_text=True),
                 SHEET_BLOCKS)
    po = _blocks(client.get(f"/purchase/view/{GOLD_PO}").get_data(as_text=True),
                 SHEET_BLOCKS)
    ra = _blocks(client.get("/ra/print/gold-ra").get_data(as_text=True),
                 SHEET_BLOCKS)

    assert ra["letterhead"] == ti["letterhead"], (
        "the RA bill and the tax invoice print different letterheads. They are "
        "the same instrument and they render through docsheet.letterhead() "
        "precisely so they cannot diverge.")

    assert pi["letterhead"] != ti["letterhead"], (
        "the proforma's letterhead now matches the tax invoice's. If the "
        "GSTIN-for-branches swap was dropped deliberately, drop "
        "docsheet.letterhead()'s `show_branches` flag with it rather than "
        "leaving a parameter nothing uses.")
    assert po["letterhead"] != ti["letterhead"], (
        "the PO's letterhead now matches the others — if that was deliberate, "
        "drop `show_web` and close ABOUT.md §7 gap 18.")

    foots = {ti["foot-strip"], pi["foot-strip"], po["foot-strip"],
             ra["foot-strip"]}
    assert len(foots) == 1, (
        f"four documents, {len(foots)} different foot strips: {foots}")


# ═══ The BOQ line picker, pinned BEFORE it is extracted ════════════════════
#
# `/po/create` is not an A4 sheet, so it gets its own marker list. The blocks
# are chosen to isolate the four things the extraction could plausibly move:
# the stylesheet stack (which carries the `.pk-*` rules), the tools bar, the
# rendered rows, and the JavaScript.

GOLD_PICK_BOQ = "gold-pick-boq"

PICKER_BLOCKS = [
    ("head",    "<head>"),
    ("intro",   '<div class="set-intro"'),
    ("vendor",  '<div class="section-title">Supplier</div>'),
    ("details", '<div class="section-title">Order details</div>'),
    ("lines",   '<div class="section-title">Lines to order</div>'),
    ("tools",   '<div class="pk-tools">'),
    ("rows",    "<tbody>"),
    ("payload", "var LINE_IDS"),
    ("js",      "function el(id)"),
]


class _FixedToday:
    """`datetime.date` with today nailed down. Only `today()` is ever called."""

    @staticmethod
    def today():
        return _real_date(2026, 8, 16)


# The collections the RAIL counts on every screen page (14 September 2026)
# that `conftest.client` does not clear between tests AND no golden fixture in
# this file owns. A form's golden reads every one of them now — `Projects 3`,
# `Employees 2` — so a fixture that pinned only the picker's own records
# rendered a different `head` block depending on which tests had run first.
# `tests/test_page_golden.py::world` holds all of them still; this is the same
# rule for the one pinned form. `ra_bills`, `boqs`, `delivery_challans`,
# `measurements`, `purchase_orders` and the sell-side four are NOT here: each
# is set by a golden fixture, and `golden_picker` depends on every one of those
# so that the form renders in the same world whichever test asks for it.
RAIL_COUNTED = ("projects", "employees", "attendance", "charges", "receipts")


@pytest.fixture()
def pinned_counts(client):
    """
    Every counted collection no golden owns, emptied — and the user table cut
    down to the signed-in test Owner alone, so `Users & Access` reads 1 — then
    put back afterwards. Used by the pinned FORM (`/po/create`); the printed
    documents render no rail and need none of this.
    """
    import auth

    saved = {k: dict(STORE.get(k) or {}) for k in RAIL_COUNTED + ("users",)}
    for k in RAIL_COUNTED:
        STORE.setdefault(k, {}).clear()
    with client.session_transaction() as session:
        me = session.get(auth.SESSION_KEY)
    # In place, never rebound: `STORE` is one shared dict and the collection
    # object may be held by reference elsewhere.
    keep = {uid: u for uid, u in saved["users"].items() if uid == me}
    STORE["users"].clear()
    STORE["users"].update(keep)
    yield
    for k, v in saved.items():
        STORE[k].clear()
        STORE[k].update(v)


@pytest.fixture()
def golden_picker(client, pinned_identity, pinned_counts, golden, golden_ra,
                  golden_dc, golden_dpo, golden_merged, golden_ms, monkeypatch):
    """
    `/po/create?boq=<id>` — the BOQ line picker, held still.

    ⚠ **It depends on EVERY other golden fixture in this file from 14 September
      2026, and the order of the parameters is the order they run.** The rail
      on this form counts every register, so its `head` block reads the RA
      bills, the challans, the sheets and the sell-side documents — and one
      digest can only hold in every test that renders it if every test renders
      it in the same world. Alone it used to see whatever the previous test
      left; beside `golden_ra` it saw one bill more. Now it always sees the
      golden world, and `pinned_counts` holds still what no golden owns.

    Captured **before** the grid was lifted out of `po_draft.py` into
    `boqpick.py`, for exactly the reason the four sheets above were captured
    before `docsheet.py` existed: a digest taken afterwards asserts only that
    the code equals itself.

    Four things on this page move on their own, and each is pinned rather than
    hashed around — a normalisation applied to the page before hashing would be
    a second thing that can be wrong:

    * the **company identity**, via `pinned_identity`;
    * **today's date**, which fills the form's date box. `po_draft._date` is
      replaced with a fixed stand-in;
    * the **draft-PO series**, which prints in the intro band as the number
      this order will take — the record is removed so the defaults stand;
    * the **address book**, which fills the vendor picker. It is one of the two
      collections `conftest.client` does not clear between tests, so it is
      snapshotted, emptied, re-seeded and put back.

    The BOQ itself is a fixed three-line schedule rather than the seeded Sify
    one: it carries a specification header with two sizes under it and one
    standalone line, which is every row shape the grid renders — folded child,
    fold point with a `spec · N items` tag, and an unparented row.
    """
    import address
    import po_draft
    import settings as SET

    monkeypatch.setattr(po_draft, "_date", _FixedToday)

    saved_addresses = dict(STORE["addresses"])
    saved_seed = STORE.get("_addr_seeded")
    saved_series = STORE["settings"].get(SET.PO_SERIES_RECORD)
    STORE["addresses"].clear()
    STORE["_addr_seeded"] = False
    address.ensure_demo_addresses()
    STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    STORE.setdefault("purchase_orders", {}).clear()

    head = {
        "line_id": "cccccccccccc", "item_no": "24", "parent_item_no": "",
        "section": "B", "is_header": True,
        "description": ("Providing and fixing MS heavy duty 'C' class pipe "
                        "conforming to IS 1239 / IS 3589, including all "
                        "fittings, supports and testing."),
        "remark": "", "unit": "", "area_qty": {}, "total_qty": 0.0,
        "supply_base_rate": None, "supply_escalation_pct": 0.0,
        "supply_rate": 0.0, "supply_amount": 0.0,
        "supply_hsn": "", "supply_gst_rate": 18.0,
        "install_base_rate": None, "install_escalation_pct": 0.0,
        "install_rate": 0.0, "install_amount": 0.0,
        "install_sac": "", "install_gst_rate": 18.0,
    }
    kid_a = dict(head, line_id="dddddddddddd", item_no="24.a",
                 parent_item_no="24", is_header=False,
                 description="80 mm dia", unit="Mtrs",
                 area_qty={"T1": 120.0}, total_qty=120.0,
                 supply_base_rate=980.0, supply_rate=1127.0,
                 supply_amount=135240.0, supply_hsn="73063090")
    kid_b = dict(kid_a, line_id="eeeeeeeeeeee", item_no="24.b",
                 description="150 mm dia", area_qty={"T1": 700.0},
                 total_qty=700.0, supply_base_rate=1760.0,
                 supply_rate=2024.0, supply_amount=1416800.0)
    loose = dict(head, line_id="ffffffffffff", item_no="31",
                 parent_item_no="", is_header=False,
                 description="Butterfly valve 80 mm, wafer type, cast iron body",
                 unit="Nos", area_qty={"T1": 4.0}, total_qty=4.0,
                 supply_base_rate=6200.0, supply_rate=7130.0,
                 supply_amount=28520.0, supply_hsn="84818030")

    STORE["boqs"][GOLD_PICK_BOQ] = {
        "id": GOLD_PICK_BOQ, "ref": "SF/BOQ/26-27/0007", "fy": "26-27",
        "date": "2026-04-01", "rev_no": 0, "supersedes": "",
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": "Prudent Teqtis Pvt Ltd\nSurvey 21, Whitefield\nBangalore, Karnataka - 560066",
        "bill_gstin": "29AABCP1234C1ZX", "ship_same": "on",
        "rate_basis_label": "Mohali Rates",
        "sections": [{"code": "B", "title": "Hydrant system", "areas": ["T1"]}],
        "line_items": [head, kid_a, kid_b, loose],
        "supply_subtotal": 1580560.0, "install_subtotal": 0.0,
        "subtotal": 1580560.0,
        "payment_terms": "", "delivery_terms": "", "notes": "",
        "company_branch": "", "auth_signatory": "",
    }

    yield

    STORE["boqs"].pop(GOLD_PICK_BOQ, None)
    STORE["purchase_orders"].clear()
    STORE["addresses"].clear()
    STORE["addresses"].update(saved_addresses)
    STORE["_addr_seeded"] = saved_seed
    if saved_series is None:
        STORE["settings"].pop(SET.PO_SERIES_RECORD, None)
    else:
        STORE["settings"][SET.PO_SERIES_RECORD] = saved_series


# Captured 16 August 2026, against the code as it stood BEFORE `boqpick.py`
# existed. These are the baseline the extraction is measured by.
GOLD_PICK_BOQ = "gold-pick"
# was 2cbe1a602a7943f6 / 54498 before the 29 Aug 2026 nav re-baseline. ⚠ This
# one is a FORM, not a printed sheet — it moved for the same +248 bytes and
# nothing about the picker itself changed: `intro`, `vendor`, `details`,
# `lines`, `tools`, `rows`, `payload` and `js` are all byte-identical.
# was c5f1a8da473a7c42 / 54746 before the 29 Aug 2026 MEASUREMENT nav entry —
# **+342 bytes, the same one anchor**, and the same eight blocks are again
# byte-identical. A form is not paper, so nothing here is a print claim; it is
# pinned because `boqpick.py` is shared and this is where a drift would show.
# was fa67dd4e4be6ee70 / 55088 before the 14 Sep 2026 SIDEBAR. ⚠ **This is the
# ONE page in this file that moved for the sidebar, and it moved because it is
# a FORM and not a printed document**: it renders the app shell, and the shell
# was redrawn. **+26,282 bytes, in the `head` block ALONE** — the shell's
# stylesheet and script, the rail, the top bar, and the user chip this page
# had been denied while its chrome was hashed beside the printed sheets.
# `intro`, `vendor`, `details`, `lines`, `tools`, `rows`, `payload` and `js` —
# the picker itself, which is what this golden exists for — are byte-identical.
# **Not one of the nine printed documents in this file moved**, because none of
# them renders the shell (commit 1); `test_no_print_route_renders_the_nav`
# below is what holds that.
# was 060391842bc9e4fc / 81370 before the 23 Sep 2026 delete rollout.
#     ⚠ **`head` ALONE moved, and every other block is byte-identical** — the
#     +462 bytes are `cascade.CASCADE_STYLES`, loaded by `/po/delete/<id>`'s
#     confirmation page so it can draw the "this also destroys N records"
#     block. It is loaded in po_draft.py's shared head, which this form
#     shares; the picker itself did not change.
PICK_WHOLE = "ad38de27596e55cc"
PICK_LEN = 81832
PICK_BLOCKS = {"head":    "b07f3fb758299248",   # was af77ecc07bfca6ff,
                                                # was 8bf28275fa127606,
                                                # was 2bf1b714db890d61,
                                                # was 04f4809335b2c9e8
               "intro":   "5558f09cc783266e",
               "vendor":  "715e7c6cd4634448",
               "details": "53b096aa21f5264c",
               "lines":   "10ed04f5fad93d1e",
               "tools":   "76ba5972ff18f235",
               "rows":    "a57b4602a006fa6f",
               "payload": "0b433e5e3f3e5705",
               "js":      "f1bae1908e487e97"}


def test_the_boq_line_picker_is_unchanged(client, golden_picker):
    """
    `/po/create?boq=<id>` — the grid `boqpick.py` was lifted out of.

    The grid is checkbox-per-line with an editable quantity, select-all /
    clear-all, and the family fold that carries a specification clause with its
    sizes. It exists in `po_draft.py`, it is wanted verbatim by the delivery
    challan, and copying it a third time is how four documents stopped looking
    like each other. So it moves into a leaf module — and this pins what
    "unchanged" means while it does.
    """
    r = client.get(f"/po/create?boq={GOLD_PICK_BOQ}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), PICK_WHOLE, PICK_LEN, PICK_BLOCKS,
           markers=PICKER_BLOCKS, what="BOQ line picker")


def test_the_picker_golden_is_hashing_a_real_form(client, golden_picker):
    """
    The control, for the same reason the four sheets have one.

    A digest assertion passes just as well against a redirect that rendered
    nothing, or against a BOQ whose lines silently failed to reach the grid.
    """
    html = client.get(f"/po/create?boq={GOLD_PICK_BOQ}").get_data(as_text=True)
    assert 'id="c_dddddddddddd"' in html, "the picker rendered no checkbox rows"
    assert 'id="q_eeeeeeeeeeee"' in html, "the quantity boxes are missing"
    assert "150 mm dia" in html, "the line descriptions did not render"
    assert "spec &middot; 2 items" in html, "the family fold did not render"
    assert "SF/DPO/0001" in html, "the series is not the pinned default"
    assert 'value="2026-08-16"' in html, "today's date was not pinned"


# ═══ The delivery challan ══════════════════════════════════════════════════

GOLD_DC = "gold-challan"


@pytest.fixture()
def golden_dc(client, pinned_identity):
    """
    One delivery challan, fixed end to end, built to their DC54.

    Built directly rather than through `/dc/create` for the reason the four
    sheets above are: the route mints a uuid and spends a number from the
    series, and neither is a thing a golden can hold still.
    """
    STORE.setdefault("delivery_challans", {}).clear()
    STORE["delivery_challans"][GOLD_DC] = {
        "id": GOLD_DC, "ref": "54", "date": "2026-07-28",
        "boq_id": "gold-boq", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "consignee_id": "", "consignee_source": "typed",
        "consignee_name": "Samruddhi Fire",
        "consignee_addr": "Sify Infinit\nBangalore",
        "consignee_phone": "95765 76713",
        "dispatch_mode": "Transport", "dispatch_to": "Bangalore",
        "po_no": "", "po_date": "", "notes": "",
        "items": [
            {"line_id": "aaaaaaaaaaaa", "is_header": False, "item_no": "1",
             "description": "80mm Butterfly valve- SANT", "unit": "Nos",
             "qty": 2.0},
            {"line_id": "bbbbbbbbbbbb", "is_header": False, "item_no": "2",
             "description": "150mm Foot valve- SANT", "unit": "Nos",
             "qty": 1.0},
            {"line_id": "cccccccccccc", "is_header": False, "item_no": "3",
             "description": "32mm Ball valve- SANT", "unit": "Nos",
             "qty": 1.0},
        ],
        "company_branch": "", "auth_signatory": "",
    }

    yield

    STORE["delivery_challans"].clear()


# Captured 16 August 2026, when `/dc/print` was built. There is no earlier
# baseline to compare against and there should not be: this is a new document,
# so the number records what shipped rather than proving nothing moved.
#
# The `letterhead` and `foot-strip` digests are deliberately the tax invoice's
# own — `850cbd…` and `cc51ac…` appear against TI_BLOCKS above. That is the
# point of the sheet, and the assertion below states it directly rather than
# leaving it to two literals happening to match.
# was d22fee5aa301c740 / 83649 before the 27 Aug 2026 escaping pass
DC_WHOLE, DC_LEN = "9face4745b37d291", 83657
DC_BLOCKS = {"head":       "f3f5e6b5c49c9e9f",
             "letterhead": "3c080a57f60c89e9",
             "foot-strip": "1efaaf73d3a0a076",
             "doc-box":    "57c1a660915be1d9",
             "party":      "429e9f10652d220b",
             "items":      "6ad4a95ae07c0108",
             "signature":  "53c1b52f4aa0c8ba"}


def test_the_delivery_challan_document_matches_its_recorded_baseline(
        client, golden_dc):
    """
    `/dc/print/<id>` — the goods-movement note, on the shared A4 sheet.

    Pinned on the same markers as the four documents above, which is itself
    part of the assertion: the challan carries the same `<head>` stylesheet
    stack, the same repeating letterhead, the same foot strip, the same framed
    `.doc-box`, the same `.doc-header` party grid, the same `.items-wrap` table
    shell and the same `.sig-block`. What differs inside those blocks is what
    DC54 differs by, and nothing else.
    """
    r = client.get(f"/dc/print/{GOLD_DC}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), DC_WHOLE, DC_LEN, DC_BLOCKS,
           what="delivery challan")


def test_the_challan_and_the_tax_invoice_carry_the_SAME_letterhead(
        client, golden, golden_dc):
    """
    The RA bill's assertion, applied to the fifth document that prints.

    A delivery challan is not a tax invoice and shares almost nothing else with
    one — no GST block, no bank block, no totals, a four-column table and a
    title band above the letterhead that no other document has. **The
    letterhead is still the same bytes**, because it is the same office, and
    the client's complaint was never that one document was wrong: it was that
    they did not look like they came from the same place.

    This is also what pins `docsheet.sheet_open(title_band=…)` to the design it
    was given. The band is a `<caption>`, which sits **before** the `<thead>`
    marker this block starts at — so the letterhead is untouched by it. Move
    the band into a second `<thead>` row and this test goes red, which is
    exactly the mistake it exists to catch.
    """
    ti = _blocks(client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True),
                 SHEET_BLOCKS)
    dc = _blocks(client.get(f"/dc/print/{GOLD_DC}").get_data(as_text=True),
                 SHEET_BLOCKS)

    assert dc["letterhead"] == ti["letterhead"], (
        "the delivery challan and the tax invoice print different letterheads. "
        "Both render through docsheet.letterhead() precisely so they cannot "
        "diverge — and if the title band is what moved it, it belongs in the "
        "<caption>, not in the <thead>.")
    assert dc["foot-strip"] == ti["foot-strip"], (
        "the challan's foot strip differs from every other document's")


def test_the_challan_golden_is_hashing_a_real_document(client, golden_dc):
    """The control. A digest passes just as well against an error page."""
    html = client.get(f"/dc/print/{GOLD_DC}").get_data(as_text=True)
    assert "DELIVERY CHALLAN" in html and "DESCRIPTION OF GOODS" in html
    assert "150mm Foot valve- SANT" in html, "the goods table rendered nothing"
    assert "Sify Infinit" in html, "the consignee block rendered nothing"
    assert "Name &amp; Signature of Receiver" in html


def test_the_goldens_are_hashing_a_real_document(client, golden, golden_ra):
    """
    The control.

    Three digest assertions pass just as well against three error pages, or
    against a fixture that silently stopped seeding. This proves each page is
    the document it claims to be before any digest is believed.
    """
    ti = client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True)
    assert "TAX INVOICE" in ti and "SF/TI/26-27/0001" in ti
    assert "84131990" in ti, "the HSN column rendered nothing"

    po = client.get(f"/purchase/view/{GOLD_PO}").get_data(as_text=True)
    assert "PURCHASE ORDER" in po and "SF/PO/26-27/0001" in po
    assert "Vishwakarma" in po, "the vendor block rendered nothing"

    bill = client.get("/ra/print/gold-ra").get_data(as_text=True)
    assert "TAX INVOICE" in bill and "73063090" in bill
    assert "150 mm dia" in bill, "the claim row rendered nothing"


# ═══════════════════════════════════════════════════════════════════════════
# THE JOINT MEASUREMENT SHEET — NEW COVERAGE, NOT A RE-BASELINE
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠ **NOTHING ABOVE THIS LINE MOVED, AND THAT IS THE POINT.** The measurement
#   sheet has never had a golden — `measurement._legacy_document_html()`'s own
#   docstring records the deliberate decision not to pin one, on the reasoning
#   that CC-2 is silent on whether a measurement prints at all and freezing an
#   unspecified design would make the client's first sight of it a re-baselining
#   exercise.
#
#   That reasoning still holds for the LEGACY sheet, which is why no golden is
#   added for it here. It does not hold for the joint sheet, because the joint
#   sheet is **transcribed from the client's own workbook** — its layout is no
#   longer a design nobody specified, it is a document they already use, and the
#   thing worth pinning is that we go on drawing theirs.
#
#   Authorised by the twenty-third §0 block of CLIENT_CHANGES.md,
#   6 September 2026. Every ruling behind the layout is recorded there as OURS.

GOLD_MS = "gold-joint-ms"


@pytest.fixture()
def golden_ms(client, pinned_identity):
    """
    One joint measurement sheet, fixed end to end.

    Built directly rather than through `/measurement/create` for the reason
    every other golden fixture is: the route mints a uuid and spends a number
    from the FY series, and neither is a thing a golden can hold still.

    ⚠ It carries **both halves** — `items` and the grid. A fixture with only
      the grid would be pinning a sheet the application cannot produce, because
      the `items` rows are what feed the installation ceiling and every real
      sheet has them.
    """
    import measurement as MS
    import settings as ST

    STORE.setdefault("measurements", {}).clear()
    STORE["measurements"][GOLD_MS] = {
        "id": GOLD_MS, "ref": "SF/MS/26-27/0007", "fy": "26-27",
        "date": "2026-09-06",
        "boq_id": "gold-boq", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "location": "", "measured_by": "R. Kadam",
        "witnessed_by": "Site engineer", "notes": "",
        "company_branch": "", "auth_signatory": "",
        "approval_status": "approved",
        "grid_model": MS.GRID_MODEL_JOINT,
        "grid_columns": [dict(c) for c in ST.DEFAULT_MEASUREMENT_COLUMNS],
        "grid_rows": [
            {"label": "H1", "values": {"d25": 12.5, "d100": 30.0, "msa": 4.0},
             "remarks": "riser at the lift lobby"},
            {"label": "SH 1", "values": {"d32": 8.0, "pendant": 6.0},
             "remarks": ""},
            {"label": "B1", "values": {"d150": 22.0, "upright": 2.0},
             "remarks": "basement main"},
        ],
        "system": "Hydrant & Sprinkler Line", "material": "MS Pipe",
        "dia_meter": "25 mm To 150 mm", "area": "All Area",
        "site_label": "Whitefield, Bangalore", "site_source": "project",
        "items": [
            {"line_id": "aaaaaaaaaaaa", "is_header": False, "item_no": "1",
             "description": "80mm Butterfly valve- SANT", "unit": "Nos",
             "qty": 2.0, "boq_qty": 4.0},
        ],
    }

    yield

    STORE["measurements"].clear()


# The joint sheet carries no `.items-wrap` and no `.sig-block` — its grid head
# is two rows deep with spanning group cells, which `docsheet.items_table()`
# cannot express, and its foot is two parties side by side rather than one
# signatory. So it is pinned on the blocks it DOES share, which is the whole of
# what it can share.
MS_SHEET_BLOCKS = [
    ("head",       "<head>"),
    ("letterhead", "<thead><tr><td>"),
    ("foot-strip", "<tfoot><tr><td>"),
    ("doc-box",    '<div class="doc-box">'),
    ("party",      '<div class="doc-header'),
]


def test_the_joint_measurement_sheet_carries_the_SAME_letterhead(
        client, golden, golden_ms):
    """
    ⚠ **THE ASSERTION THIS DOCUMENT WAS ADDED TO THE FILE FOR.**

    The standing architectural rule is that a new document derived from an
    existing chain reuses the printed layout that already exists — separate
    behaviour, shared appearance. The delivery challan's letterhead hashes
    identically to the tax invoice's and the test above is what says so; the
    joint measurement sheet now joins that set.

    A measurement is not a tax invoice and shares almost nothing else with one:
    no GST block, no bank block, no money at all, a thirteen-column grid, a
    landscape page and a two-party countersignature. **The letterhead is still
    the same bytes**, because it is the same office — and the client's
    complaint was never that one document was wrong, it was that they did not
    look like they came from the same place.
    """
    ti = _blocks(client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True),
                 SHEET_BLOCKS)
    ms = _blocks(client.get(f"/measurement/print/{GOLD_MS}").get_data(as_text=True),
                 MS_SHEET_BLOCKS)

    assert ms["letterhead"] == ti["letterhead"], (
        "the joint measurement sheet and the tax invoice print different "
        "letterheads. Both render through docsheet.letterhead() precisely so "
        "they cannot diverge — and if the title band is what moved it, it "
        "belongs in the <caption>, not in the <thead>.")
    assert ms["foot-strip"] == ti["foot-strip"], (
        "the measurement sheet's foot strip differs from every other document's")


def test_the_joint_sheet_takes_the_address_from_settings_not_a_constant(
        client, golden_ms, pinned_identity):
    """
    ⚠ **Take the address from `/settings`, never from a constant.** A second
    letterhead drawn inside `measurement.py` is exactly what `docsheet.py` was
    extracted to stop, and it had already found four that had drifted apart.
    """
    import branding as B
    html = client.get(f"/measurement/print/{GOLD_MS}").get_data(as_text=True)
    assert B.COMPANY_ADDR in html
    assert '<div class="lh-addr">' in html


def test_the_joint_sheet_golden_is_hashing_a_real_document(client, golden_ms):
    """
    The control. A digest passes just as well against an error page, and every
    other golden in this file carries one of these for that reason.
    """
    html = client.get(f"/measurement/print/{GOLD_MS}").get_data(as_text=True)

    assert "JOINT MEASUREMENT SHEET" in html
    # The five header rows.
    for label in ("SITE", "SYSTEM", "MATERIAL", "DIA METER", "AREA"):
        assert f">{label}<" in html, f"the header block is missing {label}"
    assert "Hydrant &amp; Sprinkler Line" in html
    # The grid: a spanning group head, a dia column, a unit, and a location.
    assert ">SUPPORTS<" in html and ">SPRINKLER<" in html
    assert ">PENDANT<" in html and ">UPRIGHT<" in html
    assert "200 NB" in html and "(kgs)" in html
    assert "riser at the lift lobby" in html, "the remarks column rendered nothing"
    # The TOTAL row, and figures only a real total can produce.
    assert "TOTAL" in html
    assert "12.5" in html and "22" in html
    # Both parties.
    assert html.count('class="jm-party"') == 2
    assert "Prudent Teqtis Pvt Ltd" in html


def test_the_joint_sheet_is_LANDSCAPE_and_no_other_document_became_one(
        client, golden, golden_ms):
    """
    The `@page` override is layered after the shared sheet and must reach this
    document and no other — `boq.BOQ_STYLES`'s rule, and the reason it is an
    override rather than an edit to `VIEW_DOC_STYLES`.
    """
    ms = client.get(f"/measurement/print/{GOLD_MS}").get_data(as_text=True)
    assert "A4 landscape" in ms

    for url in (f"/invoice/view/{GOLD_TI}", f"/proforma/view/{GOLD_PI}",
                f"/purchase/view/{GOLD_PO}"):
        assert "A4 landscape" not in client.get(url).get_data(as_text=True), (
            f"{url} became landscape — the measurement sheet's @page override "
            f"has leaked into the shared stylesheet")


def test_no_blank_filler_row_reaches_the_printed_sheet(client, golden_ms):
    """
    ⚠ The client's paper carries about ten ruled blanks before the TOTAL row.
    We print none. A blank ruled row underneath a countersignature is an
    invitation to write on the document after both parties have signed it — the
    delivery challan pass's argument, and stronger here because this document
    is signed by the customer too.

    ⚠ **Still needs Yogesh's confirmation**, exactly as the DC one does.
    """
    html = client.get(f"/measurement/print/{GOLD_MS}").get_data(as_text=True)
    # ⚠ Split on the GRID's own table, not on the first `<tbody>` on the page —
    #   that one belongs to `.page-frame`, the outer table the letterhead
    #   repeats through, and counting its rows measures the page furniture
    #   instead of the measurement. The first draft of this test did exactly
    #   that and reported 3 rows for a 4-row grid.
    grid = html.split('<table class="jm-grid">')[1].split("</table>")[0]
    body = grid.split("<tbody>")[1].split("</tbody>")[0]
    # Three seeded locations plus the TOTAL row, and nothing else.
    assert body.count("<tr") == 4, (
        f"the grid printed {body.count('<tr')} rows against 3 locations "
        f"plus TOTAL — a filler row has appeared")
    for label in ("H1", "SH 1", "B1", "TOTAL"):
        assert f">{label}<" in body


# ═══════════════════════════════════════════════════════════════════════════
# THE THREE PRINT ROUTES THAT HAD NO GOLDEN — pinned BEFORE the nav is stripped
# ═══════════════════════════════════════════════════════════════════════════
#
# 14 September 2026. The sidebar pass strips `_nav()` out of every print route
# so that a navigation change can never again re-baseline a printed document
# (ABOUT.md §7, "Global Nav vs Print Goldens"). That change is measured by
# this file — and three print routes were not in it:
#
#   * `/boq/print/<id>`     — the issued BOQ. Renders no nav today.
#   * `/po/print/<id>`      — the draft purchase order. Renders no nav today.
#   * `/merged/print/<id>`  — the merged tax invoice. **Renders a nav today**,
#                             and is the one of the three the strip will move.
#
# Each is pinned here, on the same markers as the documents above, in a commit
# that touches no source file beyond `dashboard.PINNED_PAGES` — the order
# `docsheet.py` and `boqpick.py` set: the baseline goes in before the change it
# measures, so the digest is an observation and not a description of the
# result.
#
# Two print routes are deliberately still NOT pinned, each with its reason:
#
#   * `/measurement/print/<id>` on a LEGACY sheet — `measurement.py`'s own
#     decision, recorded in ABOUT.md §5: CC-2 is silent on whether a
#     measurement prints, and pinning a design nobody specified would make the
#     client's first sight of it a re-baselining exercise. The JOINT sheet is
#     pinned above on the blocks it shares.
#   * `/quotation/view/<id>` — `quotation.py` is frozen (INTRODUCTION.md §7),
#     so its `_nav()` call cannot be removed and its page will follow every
#     nav change. Pinning it here would make a print golden move on every
#     chrome change by construction, which is the opposite of what a golden in
#     this file is for.

GOLD_DPO = "gold-draft-po"
GOLD_MERGED = "gold-merged"
GOLD_RA_INSTALL = "gold-ra-install"


@pytest.fixture()
def golden_dpo(client, pinned_identity):
    """
    One draft purchase order, fixed end to end — built directly, for the
    reason every other fixture here is: `/po/create` mints a uuid and spends a
    number from the `/settings` series, and neither is a thing a golden can
    hold still.
    """
    STORE.setdefault("purchase_orders", {}).clear()
    STORE["purchase_orders"][GOLD_DPO] = {
        "id": GOLD_DPO, "ref": "SF/DPO/0007", "date": "2026-07-14",
        "boq_id": "gold-boq", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "vendor_id": "", "vendor_source": "typed",
        "vendor_name": "Vishwakarma Pumps & Motors Pvt. Ltd.",
        "vendor_gstin": "33AACCV5678D1Z2",
        "to": ("Vishwakarma Pumps & Motors Pvt. Ltd.\nKind Attn: Mr S Ramanathan\n"
               "Plot 44, SIDCO Industrial Estate\nCoimbatore, Tamil Nadu - 641021"),
        "delivery_to": "Samruddhi Fire Services — Whitefield site store",
        "notes": "Please quote delivered rates.",
        "items": [
            {"line_id": "cccccccccccc", "is_header": True, "item_no": "24",
             "description": ("Providing and fixing MS heavy duty 'C' class pipe "
                             "conforming to IS 1239 / IS 3589, including all "
                             "fittings, supports and testing."),
             "unit": "", "qty": 0.0, "pcs": ""},
            {"line_id": "dddddddddddd", "is_header": False, "item_no": "24.a",
             "description": "80 mm dia", "unit": "Mtrs", "qty": 120.0, "pcs": "20"},
            {"line_id": "eeeeeeeeeeee", "is_header": False, "item_no": "24.b",
             "description": "150 mm dia", "unit": "Mtrs", "qty": 700.0, "pcs": ""},
        ],
        "converted_po_ids": [],
        "company_branch": "", "auth_signatory": "",
    }

    yield

    STORE["purchase_orders"].clear()


@pytest.fixture()
def golden_merged(client, golden_ra):
    """
    One merged tax invoice over the golden supply bill and a second,
    installation-leg bill on the same schedule.

    Built directly rather than through `/merged/create` because the route
    mints the `MI` serial and the record id, and `merged_ra.create()` reads
    today's date. The record shape is ABOUT.md §3's, field for field; the
    totals are the two bills' stored totals added, which is what
    `merged_ra._sum_totals()` does and what the document prints.
    """
    import ra

    child = STORE["boqs"]["gold-boq"]["line_items"][1]
    c = ra.build_claim(child, 50.0, 1200.0, 0.0, 1200.0, leg="installation",
                       hsn_sac="995462", gst_rate=18.0)
    subtotal, drows, dtotal, net = ra.bill_totals([c], [])
    tax = ra.compute_tax_totals([c], [], "cgst_sgst", 9.0, 9.0, 18.0)
    inst = {
        "id": GOLD_RA_INSTALL, "ref": "SF/RA/26-27/0003", "fy": "26-27",
        "date": "2026-06-12",
        "tax_invoice_ref": "SF/RI/26-27/0002", "tax_invoice_date": "2026-06-12",
        "po_ref": "PT/WO/2026/44", "po_date": "2026-03-28",
        "boq_id": "gold-boq", "boq_ref": "SF/BOQ/26-27/0001", "boq_rev_no": 0,
        "ra_no": 3, "leg": "installation",
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": STORE["boqs"]["gold-boq"]["to"],
        "bill_gstin": "29AABCP1234C1ZX",
        "claims": [c], "claim_subtotal": subtotal,
        "deductions": drows, "deduction_total": dtotal, "net_payable": net,
        "prev_balance": 0.0, "prev_balance_refs": [],
        "status": "issued", "issued_on": "2026-06-12",
        "cancelled_on": "", "cancel_reason": "",
        "notes": "", "company_branch": "", "auth_signatory": "",
        "approval_status": "approved",
    }
    inst.update(tax)
    STORE["ra_bills"][GOLD_RA_INSTALL] = inst

    sup = STORE["ra_bills"]["gold-ra"]
    summed = {k: round(float(sup.get(k) or 0.0) + float(inst.get(k) or 0.0), 2)
              for k in ("claim_subtotal", "deduction_total", "net_payable",
                        "tax_amount", "rounding_off", "grand_total")}
    STORE.setdefault("merged_ras", {}).clear()
    STORE["merged_ras"][GOLD_MERGED] = {
        "id": GOLD_MERGED,
        "tax_invoice_ref": "SF/MI/26-27/0001", "fy": "26-27", "date": "2026-06-20",
        "supply_ra_id": "gold-ra", "installation_ra_id": GOLD_RA_INSTALL,
        "supply_ref": sup["ref"], "installation_ref": inst["ref"],
        "supply_ra_no": 2, "installation_ra_no": 3,
        "boq_id": "gold-boq", "boq_ref": "SF/BOQ/26-27/0001",
        "project_name": "Sify Bangalore — Fire Protection",
        "site_location": "Whitefield, Bangalore",
        "account_name": "Prudent Teqtis Pvt Ltd", "contact_person": "Mr R Nair",
        "to": STORE["boqs"]["gold-boq"]["to"], "bill_gstin": "29AABCP1234C1ZX",
        **summed,
        "status": "live", "cancelled_on": "", "cancel_reason": "", "notes": "",
        # APPROVED — B7. An approved document emits no print-blanking block,
        # exactly as the RA golden above records.
        "approval_status": "approved",
    }

    yield

    STORE["merged_ras"].clear()


# The BOQ writes its own letterhead inside `boq._document_html()` and carries
# no `.items-wrap` — its body is one `.boq-table` per section and a separate
# `.boq-grand` for the totals — so it is split on the blocks it does carry.
BOQ_SHEET_BLOCKS = [
    ("head",       "<head>"),
    ("letterhead", "<thead><tr><td>"),
    ("foot-strip", "<tfoot><tr><td>"),
    ("doc-box",    '<div class="doc-box">'),
    ("party",      '<div class="doc-header'),
    ("sections",   '<table class="boq-table">'),
    ("grand",      '<div class="boq-grand">'),
    ("signature",  '<div class="sig-block">'),
]

# Captured 14 September 2026, against the code as it stood BEFORE the nav was
# stripped out of the print routes. The BOQ and the draft PO render no nav, so
# neither is expected to move; the merged tax invoice renders one and is
# expected to move in the `head` block ALONE.
#
# Re-baselined 20 September 2026 — the sheet learns to fit a portrait page
# (`boq.BOQ_DOC_STYLES` / `BOQ_DOC_SCRIPT`, ABOUT.md §5 `/boq`). The owner's
# phone printed the landscape page box scaled onto portrait paper: every page
# 55% full, everything at 73%. Two blocks moved, +3,006 bytes in all:
#   * `head` — `BOQ_DOC_STYLES` and `BOQ_DOC_SCRIPT` are loaded after
#     `BOQ_STYLES`, and the action bar's button reads `Print` rather than
#     `Print (landscape)` — the paper is no longer always landscape.
#   * `sections` — every `<col style="width:12mm"/>` became
#     `<col class="cw-sno"/>`: the same widths, restated as classes so a
#     media query can reach them. On a desktop browser the landscape sheet is
#     drawn at exactly the widths it always was.
# `letterhead`, `foot-strip`, `doc-box`, `party`, `grand` and `signature` are
# untouched, and so is every other document in this file — `BOQ_STYLES`
# itself is byte-identical, which is why the four register pages that load
# it (`tests/test_page_golden.py`) did not move either.
# Was 6083201b22f6d952 / 100879 with head 738417a9ea306621 and sections
# 1d50afce5c49c30c.
BOQ_WHOLE, BOQ_LEN = "8c59fc3c47f82c7d", 103885
BOQ_BLOCKS = {"head":       "c945d7ee01ba87eb",
              "letterhead": "1c197f96af8ad872",
              "foot-strip": "0f66996df1483847",
              "doc-box":    "64fcaef781b20ed2",
              "party":      "9b34f96c4ac7cd01",
              "sections":   "2e4d91620fb69579",
              "grand":      "2599e3fd773e385a",
              "signature":  "7812a7b5e2ddb967"}

DPO_WHOLE, DPO_LEN = "05e26ae227bb678e", 83807
DPO_BLOCKS = {"head":       "9c5d3f7bb956b98a",
              "letterhead": "2800166c693cc2f1",
              "foot-strip": "1efaaf73d3a0a076",
              "doc-box":    "9370df26fb1e5084",
              "party":      "9d89e73813bb61f7",
              "items":      "bb3a316d1cd1b2cc",
              "signature":  "66c13b84cc80040d"}

# The merged sheet writes its party block straight into the page frame with no
# `.doc-box` around it — `merged_ra.print_merged()` opens the sheet and goes
# directly to `DS.party_block()` — so it is split on the six markers it does
# carry. Its letterhead and foot strip are the tax invoice's own bytes, which
# the SAME-letterhead assertion below states directly.
MERGED_SHEET_BLOCKS = [m for m in SHEET_BLOCKS if m[0] != "doc-box"]

# ⚠ Captured with the page's endpoint already in `dashboard.PINNED_PAGES`, so
#   the user chip is suppressed on it as on every other pinned page. Rendered
#   with the chip drawn it measured 952ab4f8fdd3952f / 97,994 bytes — the
#   1,370-byte difference is `USER_CHIP_STYLES` plus the chip's markup, and it
#   sat inside `<nav>…</nav>`; every other block was identical either way.
# was 97a995ac5d639c13 / 96624 before the 14 Sep 2026 nav removal — the one of
# the three newly pinned documents that rendered a nav, and it moved by the
# same −9,297 bytes in the `head` block alone as the four above.
#
# Re-baselined 15 September 2026 — `merged_ra.print_merged()` was appending
# `sum_row()`/`total_row()` (bare `<tr>` fragments) to `sheet` AFTER
# `DS.items_table()` had already closed its `<table>`, instead of folding them
# into the `rows_html` `items_table()` is built from, as `invoice.py` and
# `ra.py` both do. A `<tr>` outside any `<table>` is invalid HTML, and the
# browser's foster-parenting recovery hoisted `amount_words`/`bank_block`/
# `sig_block` — the content that followed the stray `<tr>`s — to BEFORE the
# whole `<table class="page-frame">`, which is what a user saw as the bank and
# signature panel printing above the letterhead. Fixed by moving the totals
# rows into `items_table()`'s argument; the missing `DS.BAND_CSS` (for the
# title band's caption styling) and the missing `.quotation-doc` wrapper (for
# every `.quotation-doc`-scoped rule, `.bank-box` included) were fixed
# alongside it since they were dead for the same reason no other document hits
# — this was the only print route where the totals rows left the table. Was
# 2f7780400388d366 / 87327 before the fix; `letterhead`, `foot-strip` and
# `party` are untouched by it.
MERGED_WHOLE, MERGED_LEN = "50e27290a88a97ef", 87957
MERGED_BLOCKS = {"head":       "1e9bbe98af7f4e8d",   # was e38255e4e2ed0d90
                 "letterhead": "3c080a57f60c89e9",
                 "foot-strip": "11c5bd67c2fabaa9",
                 "party":      "aa58dd01cfddecc3",
                 "items":      "e0f2b72ef4632192",   # was 30ecad09926182e7
                 "signature":  "0598f5bb4f174a53"}   # was d5b89b346e0b46ff


def test_the_boq_document_matches_its_recorded_baseline(client, golden_ra):
    """`/boq/print/<id>` — the issued schedule, no rate breakup. Must not move."""
    r = client.get("/boq/print/gold-boq")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), BOQ_WHOLE, BOQ_LEN, BOQ_BLOCKS,
           markers=BOQ_SHEET_BLOCKS, what="BOQ")


def test_the_draft_po_document_matches_its_recorded_baseline(client, golden_dpo):
    """`/po/print/<id>` — the rate-less draft order, on the shared sheet."""
    r = client.get(f"/po/print/{GOLD_DPO}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), DPO_WHOLE, DPO_LEN, DPO_BLOCKS,
           what="draft purchase order")


def test_the_merged_tax_invoice_matches_its_recorded_baseline(client, golden_merged):
    """`/merged/print/<id>` — both legs stacked under one `MI` serial."""
    r = client.get(f"/merged/print/{GOLD_MERGED}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), MERGED_WHOLE, MERGED_LEN, MERGED_BLOCKS,
           markers=MERGED_SHEET_BLOCKS, what="merged tax invoice")


def test_the_three_newly_pinned_goldens_are_hashing_real_documents(
        client, golden_ra, golden_dpo, golden_merged):
    """The control, as every golden here carries one."""
    boq = client.get("/boq/print/gold-boq").get_data(as_text=True)
    assert "BILL OF QUANTITIES" in boq and "SF/BOQ/26-27/0001" in boq
    assert "150 mm dia" in boq, "the BOQ section table rendered nothing"
    assert "Mohali Rates" not in boq, "the print must not carry the rate basis"

    dpo = client.get(f"/po/print/{GOLD_DPO}").get_data(as_text=True)
    assert "DRAFT PURCHASE ORDER" in dpo and "SF/DPO/0007" in dpo
    assert "Vishwakarma" in dpo, "the supplier block rendered nothing"
    assert "80 mm dia" in dpo, "the picked lines rendered nothing"

    merged = client.get(f"/merged/print/{GOLD_MERGED}").get_data(as_text=True)
    assert "MERGED TAX INVOICE" in merged and "SF/MI/26-27/0001" in merged
    assert "SUPPLY" in merged and "INSTALLATION" in merged, "a leg is missing"
    assert "995462" in merged, "the installation SAC rendered nothing"


def test_the_merged_tax_invoice_and_the_tax_invoice_carry_the_SAME_letterhead(
        client, golden, golden_merged):
    """
    The assertion every document that prints through `docsheet.py` carries. A
    merged tax invoice IS a tax invoice — Rule 46 wants the same GSTIN on its
    face — so its letterhead must hash to the tax invoice's own bytes.
    """
    ti = _blocks(client.get(f"/invoice/view/{GOLD_TI}").get_data(as_text=True),
                 SHEET_BLOCKS)
    mi = _blocks(client.get(f"/merged/print/{GOLD_MERGED}").get_data(as_text=True),
                 MERGED_SHEET_BLOCKS)
    assert mi["letterhead"] == ti["letterhead"], (
        "the merged tax invoice and the tax invoice print different letterheads")
    # The foot strip is NOT compared: on this sheet the block after
    # `<tfoot><tr><td>` runs to the party block rather than to a `.doc-box`,
    # so the two spans are not the same bytes even when the strip itself is.


# ═══════════════════════════════════════════════════════════════════════════
# NO PRINT ROUTE RENDERS THE NAV — 14 September 2026
# ═══════════════════════════════════════════════════════════════════════════
#
# The pieces of app chrome that `_nav()` emits. Asserted on the MARKUP and not
# on the CSS: `DS.SHEET_STYLES` still opens with `BASE_STYLES`, which carries
# the `.nav-brand` rule, so a stylesheet match would fail every sheet for a
# rule that draws nothing. What must be absent is the element.
NAV_MARKUP = ("<nav>", "<nav ", 'class="nav-brand"', 'class="nav-link"',
              'class="nav-user"', 'class="db-down"')


@pytest.mark.parametrize("name,url", [
    ("tax invoice",        f"/invoice/view/{GOLD_TI}"),
    ("proforma",           f"/proforma/view/{GOLD_PI}"),
    ("purchase order",     f"/purchase/view/{GOLD_PO}"),
    ("RA bill",            "/ra/print/gold-ra"),
    ("merged tax invoice", f"/merged/print/{GOLD_MERGED}"),
    ("delivery challan",   f"/dc/print/{GOLD_DC}"),
    ("BOQ",                "/boq/print/gold-boq"),
    ("draft PO",           f"/po/print/{GOLD_DPO}"),
    ("measurement sheet",  f"/measurement/print/{GOLD_MS}"),
])
def test_no_print_route_renders_the_nav(
        name, url, client, golden, golden_ra, golden_dc, golden_dpo,
        golden_merged, golden_ms):
    """
    ⚠ **The assertion that ends the nav/golden coupling, stated directly.**

    Until 14 September 2026 five of these documents embedded `_nav()` and hid
    it with CSS at print, so **every** navigation change moved their recorded
    digests — for a cosmetic reason, on documents that go to a client. Two
    re-baselines in one week (`Employees`, then `Measurements`) cost ten digest
    updates between them. The fix ABOUT.md §7 prescribed all along was the
    challan's shape: the document alone behind a `.no-print` action bar, with
    no nav at all. Every print route has that shape now, and this is what
    stops the nav coming back — a `{_nav()}` re-added to any of these pages
    fails here by name rather than by a golden moving for no visible reason.

    ⚠ `/quotation/view/<id>` is NOT in the list, and that is a known gap
    rather than an oversight: `quotation.py` is frozen (INTRODUCTION.md §7),
    so its `_nav()` call stays until that file is next unfrozen. It is not
    pinned by a golden either, so no printed document's digest is coupled to
    the nav through it.
    """
    html = client.get(url).get_data(as_text=True)
    assert "<html" in html, f"{name}: {url} did not render a page"
    for token in NAV_MARKUP:
        assert token not in html, (
            f"{name}: {url} renders app chrome ({token!r}). A print route is the "
            f"document alone behind a `.no-print` action bar — /dc/print's shape "
            f"— and never calls _nav(). Re-adding it re-couples every printed "
            f"document's golden to the navigation, which is the gap this closed.")
