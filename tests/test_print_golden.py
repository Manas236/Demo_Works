"""
The three printed documents, pinned byte-for-byte.

This file exists for one job: to prove that extracting the shared document
presentation layer (`docsheet.py`) changed **nothing visible** on the two
documents that already existed and must not move — the tax invoice and the
purchase order. It was written and committed BEFORE that extraction, so the
baseline is a real observation rather than a description of the result.

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
    ("party",      '<div class="doc-header">'),
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

# Captured 15 August 2026, against the code as it stood BEFORE `docsheet.py`
# existed. These three numbers are the baseline the extraction is measured by.
TI_WHOLE, TI_LEN = "def697b1652ca51f", 110082
TI_BLOCKS = {"head":       "ed18381f6fc165b7",
             "letterhead": "850cbd4766b608c2",
             "foot-strip": "cc51ac98a541aaee",
             "doc-box":    "5e4d6a24b0a5b726",
             "party":      "a7c0e4ecf0b1491f",
             "items":      "ace24562781a2e31",
             "signature":  "f5511fad8e1212cc"}

PO_WHOLE, PO_LEN = "2af89ab327a2a5ba", 101674
PO_BLOCKS = {"head":       "91a7e4c4a836e219",
             "letterhead": "350d4e9032d16839",
             "foot-strip": "cc51ac98a541aaee",
             "doc-box":    "ffe286e7afd8c90b",
             "party":      "307d35714073c084",
             "items":      "fd759d99cf4b162a",
             "signature":  "5717ca48143d8b6e"}

RA_WHOLE, RA_LEN = "88a55e81022ec48a", 53382


def test_the_tax_invoice_document_is_unchanged(client, golden):
    """`/invoice/view/<id>` — the Rule 46 sheet. Must not move."""
    r = client.get(f"/invoice/view/{GOLD_TI}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), TI_WHOLE, TI_LEN, TI_BLOCKS,
           what="tax invoice")


def test_the_purchase_order_document_is_unchanged(client, golden):
    """`/purchase/view/<id>` — the buy-side sheet. Must not move."""
    r = client.get(f"/purchase/view/{GOLD_PO}")
    assert r.status_code == 200
    _check(r.get_data(as_text=True), PO_WHOLE, PO_LEN, PO_BLOCKS,
           what="purchase order")


def test_the_ra_bill_document_matches_its_recorded_baseline(client, golden_ra):
    """
    `/ra/print/<id>` — the RA bill tax invoice.

    Unlike the two above, this one is **expected to change** in the step that
    renders it through the shared layer. The digest is here so that the change
    is a deliberate act with a number attached to it rather than something
    nobody measured.
    """
    r = client.get("/ra/print/gold-ra")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    got_len, got_whole = len(html), _sha(html)
    assert (got_whole, got_len) == (RA_WHOLE, RA_LEN), (
        f"RA bill: sha {RA_WHOLE} -> {got_whole}, "
        f"bytes {RA_LEN} -> {got_len}.")


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
