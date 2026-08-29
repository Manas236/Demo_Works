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
GOLD_TI = "gold-ti"
# was ab555e45cd245fa5 / 110208 before the 27 Aug 2026 escaping pass
# was f91031b44e1e7dc7 / 110216 before the 29 Aug 2026 nav re-baseline
TI_WHOLE = "92903e2e6134597b"
TI_LEN = 110464
TI_BLOCKS = {"head":       "f76089afb5505200",   # was 49524db46e29dcc5
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
# was 0b7ed84b19fa2646 / 106559 before the 29 Aug 2026 nav re-baseline
PO_WHOLE, PO_LEN = "a7b30226a545aa62", 106807
PO_BLOCKS = {"head":       "09c8c69b2580ee92",   # was 823a24d818d5f0c3,
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
PI_WHOLE = "9a509c8c1f87ce5c"
PI_LEN = 104029
PI_BLOCKS = {"head":       "0250890a6d6e2f6b",   # was a3b342e73adf07fc
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
RA_WHOLE = "7f964e7dceb2699f"
RA_LEN = 97912
RA_BLOCKS = {"head":       "924f39af975d8d7b",   # was ea1ccbaa59c99616
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


@pytest.fixture()
def golden_picker(client, pinned_identity, monkeypatch):
    """
    `/po/create?boq=<id>` — the BOQ line picker, held still.

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
PICK_WHOLE = "c5f1a8da473a7c42"
PICK_LEN = 54746
PICK_BLOCKS = {"head":    "2bf1b714db890d61",   # was 04f4809335b2c9e8
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
