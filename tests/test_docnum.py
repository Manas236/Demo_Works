"""
A document number typed by hand, forward only — item A of the 27 October 2026
call (CLIENT_CHANGES.md §0's **fifty-fourth** block).

What this file holds to, and why each one is here rather than assumed:

1.  the create form **prefills** the next automatic number, with the prefix
    and the financial year as un-postable text and only the tail typeable;
2.  a number **strictly greater** than the highest ever used is accepted;
    **equal** is refused; **lower** is refused; and the refusal **names** the
    current highest, because an error that says only "invalid" costs somebody
    an afternoon (INTRODUCTION.md §2);
3.  keeping the **prefilled default** is always allowed, for everybody;
4.  a **cancelled** document's number counts as used;
5.  a **deleted** document's number counts as used — this is the one the scan
    alone cannot answer, and the high-water ledger is why it can;
6.  on save the counter moves to **entered + 1**, so a skipped number is never
    handed out later;
7.  the tax invoice's check scans **all four places a TI number can be** — an
    RA bill's `tax_invoice_ref` at 0007 blocks a TI override to 0007, and to
    0005 when 0007 is the highest;
8.  the **permission** is enforced on the POST, not only by a read-only
    attribute on the field;
9.  an **issued** document's number is immutable, and a Draft purchase order's
    is not.

⚠ Every guard here is proved **non-vacuous by mutation** — see the mutation
  list in `test_the_guards_are_not_vacuous`'s docstring and the run report.
  An assertion that would pass against a blank page or a no-op validator is
  not an assertion.
"""

import json

import pytest

import auth
import challan as CH
import demo_data as DD
import docnum as DN
import invoice as INV
import proforma as PF
import purchase as PUR
import series as SER
import settings as SET
from store import STORE


# ═══════════════════════════════════════════════════════════════════════════
# 1. THE LEAF — the rule, against the store directly
# ═══════════════════════════════════════════════════════════════════════════

FY = "26-27"


@pytest.fixture()
def store(client):
    """A signed-in Owner over a fresh STORE, with the four collections empty."""
    for name in ("invoices", "proformas", "purchases", "ra_bills",
                 "merged_ras", "delivery_challans"):
        STORE.setdefault(name, {}).clear()
    STORE.setdefault("settings", {}).pop(DN.HIGHWATER_RECORD, None)
    STORE["settings"].pop(DN.DC_SERIES_RECORD, None)
    return client


def _ti(ref, fy=FY, **extra):
    rec = {"id": ref, "ref": ref, "fy": fy, "date": "2026-08-20"}
    rec.update(extra)
    STORE["invoices"][ref] = rec
    return rec


# ── the ordinal reader ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("SF/TI/26-27/0007", 7),
    ("TI/26-27/0012", 12),
    ("PI-0007", 7),
    ("54", 54),
    ("", 0),
    (None, 0),
    ("SF/TI/26-27/", 0),
    ("SF/TI/26-27/00x7", 0),
])
def test_the_ordinal_is_read_off_the_tail(raw, want):
    assert DN.ordinal_of(raw) == want


@pytest.mark.parametrize("raw,fallback,want", [
    # ⚠ The STRING wins over the record's own `fy`. This is ABOUT.md §7 gap
    #   32's live record: a `tax_invoice_ref` typed onto a bill may belong to
    #   another year entirely, and `series.py`'s SERIES_PREFIX mode exists for
    #   the same reason.
    ("SF/TI/26-27/0007", "27-28", "26-27"),
    ("SF/RI/25-26/0003", "26-27", "25-26"),
    # No year segment at all → the record's key is the only answer there is.
    ("PI-0007", "26-27", "26-27"),
    ("54", "26-27", "26-27"),
])
def test_the_financial_year_is_read_off_the_string_first(raw, fallback, want):
    assert DN.fy_of_ref(raw, fallback) == want


@pytest.mark.parametrize("ref,want", [
    ("SF/TI/26-27/0001", ("SF/TI/26-27/", "0001")),
    ("PI-0007", ("PI-", "0007")),
    ("54", ("", "54")),
    ("", ("", "")),
])
def test_the_fixed_part_and_the_typeable_part_are_split_on_the_last_separator(ref, want):
    assert DN.split_ref(ref) == want


# ── forward only ───────────────────────────────────────────────────────────

def test_a_number_ahead_of_the_highest_is_accepted(store):
    _ti("SF/TI/26-27/0007")
    seq, err = DN.validate(DN.TI, FY, "8", default_n=8, may_override=True)
    assert (seq, err) == (8, "")
    seq, err = DN.validate(DN.TI, FY, "150", default_n=8, may_override=True)
    assert seq == 150 and err == ""


def test_a_number_EQUAL_to_the_highest_is_refused_and_the_highest_is_named(store):
    _ti("SF/TI/26-27/0007")
    seq, err = DN.validate(DN.TI, FY, "7", default_n=8, may_override=True)
    assert seq == 7, "the typed value comes back so the form can re-render it"
    assert "0007" in err and "not available" in err
    assert "0008" in err, "the refusal has to say what WOULD be accepted"


def test_a_number_BELOW_the_highest_is_refused(store):
    _ti("SF/TI/26-27/0007")
    _seq, err = DN.validate(DN.TI, FY, "5", default_n=8, may_override=True)
    assert "0005" in err and "0007" in err


def test_keeping_the_prefilled_default_is_always_allowed(store):
    """
    ⚠ **Even when the default is at or below the highest ever used**, which
    is reachable: the automatic minter scans `invoices` alone and the tax
    invoice's `highest_used()` scans four collections. Refusing the prefill
    would make the form unusable for a number nobody typed.
    """
    STORE["ra_bills"]["r1"] = {"id": "r1", "fy": FY,
                               "tax_invoice_ref": "SF/RI/26-27/0007"}
    assert DN.highest_used(DN.TI, FY) == 7
    # The automatic minter knows nothing of the RA bill and prefills 0001.
    seq, err = DN.validate(DN.TI, FY, "1", default_n=1, may_override=True)
    assert (seq, err) == (1, "")
    # And a blank box is the default too.
    assert DN.validate(DN.TI, FY, "", default_n=1, may_override=True) == (1, "")


def test_text_typed_into_the_number_box_is_refused_by_shape(store):
    seq, err = DN.validate(DN.TI, FY, "00O1", default_n=1, may_override=True)
    assert seq == 1 and "digits only" in err


# ── cancelled and deleted both count ───────────────────────────────────────

def test_a_cancelled_tax_invoice_number_still_counts_as_used(store):
    """
    A GST series has to stay consecutive: a withdrawn tax invoice is CANCELLED
    rather than deleted, its record stays in `invoices`, and its serial is
    spent. `scanned_max()` filters on nothing for exactly this reason.
    """
    _ti("SF/TI/26-27/0007", status="cancelled")
    assert DN.highest_used(DN.TI, FY) == 7
    _seq, err = DN.validate(DN.TI, FY, "7", default_n=1, may_override=True)
    assert "not available" in err


def test_a_deleted_number_still_counts_as_used(store):
    """
    ⚠ **The one the scan alone cannot answer.** Delete the record and the
    scan drops back; the ledger does not. The paper carrying that number has
    already left the building.
    """
    DN.note_used(DN.PI, "", 50)
    STORE["proformas"].clear()
    assert DN.highest_used(DN.PI, "") == 50
    _seq, err = DN.validate(DN.PI, "", "50", default_n=1, may_override=True)
    assert "0050" in err and "not available" in err
    assert DN.validate(DN.PI, "", "51", default_n=1, may_override=True)[1] == ""


def test_the_ledger_only_ever_rises(store):
    DN.note_used(DN.PI, "", 50)
    DN.note_used(DN.PI, "", 20)
    assert DN.highwater()["PI"][DN.GLOBAL_SCOPE] == 50
    DN.note_used(DN.PI, "", 0)
    DN.note_used(DN.PI, "", "nonsense")
    assert DN.highwater()["PI"][DN.GLOBAL_SCOPE] == 50


def test_an_fy_scoped_ledger_does_not_reach_the_next_year(store):
    """
    April's reset under Rule 46(b) survives — the same rule `series.floor_of()`
    holds to, and for the same reason: a figure filed under `26-27` answers
    nothing when `27-28` is asked for.
    """
    DN.note_used(DN.TI, "26-27", 90)
    assert DN.highest_used(DN.TI, "26-27") == 90
    assert DN.highest_used(DN.TI, "27-28") == 0


# ── the tax invoice's four-place scan ──────────────────────────────────────

def test_an_RA_tax_invoice_ref_blocks_a_TI_override_to_the_same_number(store):
    """
    ⚠ **The brief's own case.** `ra.py` may never import `invoice.py`, so the
    scan that sees both lives in the leaf. An RA bill's statutory serial at
    0007 is a number that has gone out; a tax invoice may not repeat it.
    """
    STORE["ra_bills"]["r1"] = {"id": "r1", "fy": FY,
                               "tax_invoice_ref": "SF/RI/26-27/0007"}
    assert DN.highest_used(DN.TI, FY) == 7
    _seq, err = DN.validate(DN.TI, FY, "7", default_n=1, may_override=True)
    assert "0007" in err and "not available" in err
    # …and to 0005, which is below the highest rather than equal to it.
    _seq, err = DN.validate(DN.TI, FY, "5", default_n=1, may_override=True)
    assert "0005" in err and "0007" in err


def test_a_merged_RA_tax_invoice_ref_counts_too(store):
    STORE["merged_ras"]["m1"] = {"id": "m1", "fy": FY,
                                 "tax_invoice_ref": "SF/MI/26-27/0011"}
    assert DN.highest_used(DN.TI, FY) == 11


def test_a_TI_raised_from_a_BOQ_is_in_the_same_collection_and_the_same_scan(store):
    """
    The brief names "TIs from BOQ" as a fourth source. They are not a fourth
    collection: `invoice.from_boq()` writes an ordinary TI into
    `STORE["invoices"]`. Asserted rather than left implicit, because a reader
    counting four names and three entries in `TI_SOURCES` has to be able to
    see why.
    """
    assert [c for c, _f in DN.TI_SOURCES] == ["invoices", "ra_bills",
                                              "merged_ras"]
    _ti("SF/TI/26-27/0004", boq_id="b1", boq_ref="SF/BOQ/26-27/0001")
    assert DN.highest_used(DN.TI, FY) == 4


def test_a_typed_ref_from_ANOTHER_year_does_not_block_this_one(store):
    """Gap 32's record, read the way the leaf reads it."""
    STORE["ra_bills"]["r1"] = {"id": "r1", "fy": "26-27",
                               "tax_invoice_ref": "SF/TI/25-26/0099"}
    assert DN.highest_used(DN.TI, "26-27") == 0
    assert DN.highest_used(DN.TI, "25-26") == 99


def test_the_proforma_and_the_PO_do_NOT_scan_the_tax_invoice_sources(store):
    """
    The widening is the tax invoice's alone. A PI is a request for money, not
    a tax document, and a PO is our own buy-side book.
    """
    STORE["ra_bills"]["r1"] = {"id": "r1", "fy": FY,
                               "tax_invoice_ref": "SF/RI/26-27/0007"}
    assert DN.highest_used(DN.PI, "") == 0
    assert DN.highest_used(DN.PO, FY) == 0


# ── the challan's stored counter ───────────────────────────────────────────

def test_the_challan_reads_its_STORED_high_water_counter(store):
    """
    `challan.next_ref()`'s comment is explicit that deleting a challan SPENDS
    its number, so the counter at /settings already means "highest ever used
    + 1" and is read as such — with no challan records at all.
    """
    SET.save_dc_series("", 55)
    STORE["delivery_challans"].clear()
    assert DN.highest_used(DN.DC, "") == 54
    _seq, err = DN.validate(DN.DC, "", "54", default_n=55, may_override=True)
    assert "0054" in err


# ═══════════════════════════════════════════════════════════════════════════
# 2. THE PERMISSION
# ═══════════════════════════════════════════════════════════════════════════

def test_the_permission_is_in_the_catalogue_on_the_admin_tier():
    label, group = auth.PERMISSIONS["docnum.override"]
    assert group == "Administration"
    assert "by hand" in label


def test_owner_and_director_hold_it_by_default_and_nobody_else():
    held = sorted(slug for slug, (_n, perms) in auth.BUILTIN_ROLES.items()
                  if "docnum.override" in perms)
    assert held == ["director", "owner"]


def test_it_is_a_declared_panel_permission_and_gates_no_route():
    assert "docnum.override" in auth.PANEL_PERMISSIONS
    assert "docnum.override" not in set(auth.ROUTE_PERMISSIONS.values())


def test_without_the_permission_the_server_refuses_a_CHANGED_number(store):
    """
    ⚠ **The half a read-only attribute cannot give you.** A disabled input is
    re-enabled in a browser's inspector in four seconds; this is the rule.
    """
    seq, err = DN.validate(DN.TI, FY, "900", default_n=1, may_override=False)
    assert seq == 1, "the refused POST falls back to the automatic number"
    assert "permission" in err


def test_without_the_permission_the_DEFAULT_still_saves(store):
    """Somebody who may not type a number still has to be able to save."""
    assert DN.validate(DN.TI, FY, "1", default_n=1, may_override=False) == (1, "")
    assert DN.validate(DN.TI, FY, "", default_n=1, may_override=False) == (1, "")


# ═══════════════════════════════════════════════════════════════════════════
# 3. THE ROUTES — end to end
# ═══════════════════════════════════════════════════════════════════════════

def _sign_in_as(client, slug):
    """A user holding exactly one builtin role."""
    uid = f"dn-{slug}"
    STORE["users"][uid] = {
        "id": uid, "username": f"{slug}@test", "display_name": f"Test {slug}",
        "password_hash": "not-a-hash", "role_ids": [f"role-{slug}"],
        "active": True, "created_at": "2026-08-01 09:00", "created_by": "test",
    }
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = uid
    return uid


# ── the delivery challan: the simplest of the four to raise ────────────────

@pytest.fixture()
def sched(store):
    """The seeded 97-line schedule; its id."""
    store.get("/boq/")
    store.get("/settings/")
    return DD.BOQ_META["id"]


def _dc_payload(bid, n=1):
    """One child line off the seeded schedule — `test_boq_raise_all.py`'s
    `_family()`, which reads the header map rather than guessing a key."""
    import boq as BQ

    lines = STORE["boqs"][bid]["line_items"]
    heads = BQ.header_of(lines)
    first = min(heads)
    picked = [lines[i] for i in sorted(heads) if heads[i] == heads[first]][:n]
    assert picked, "the seeded schedule has no pickable line"
    return json.dumps({"lines": [{"line_id": r["line_id"], "qty": "1"}
                                 for r in picked]})


def _dc_post(client, bid, **extra):
    form = {"date": "2026-10-27", "dispatch_mode": "By Road",
            "consignee_name": "Samruddhi Fire", "consignee_addr": "Navi Mumbai",
            "dc_json": _dc_payload(bid)}
    form.update(extra)
    return client.post(f"/dc/create?boq={bid}", data=form)


def test_the_challan_form_prefills_the_next_number(store, sched):
    html = store.get(f"/dc/create?boq={sched}").get_data(as_text=True)
    assert 'name="doc_no_seq"' in html
    assert 'value="1"' in html, "the series starts at 1 on an empty store"
    assert "readonly" not in html.split('name="doc_no_seq"')[1][:200], (
        "an Owner holds docnum.override, so the box is typeable")


def test_the_challan_number_can_be_set_forward_and_the_counter_follows(store, sched):
    r = _dc_post(store, sched, doc_no_seq="120")
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    dc = next(iter(STORE["delivery_challans"].values()))
    assert dc["ref"] == "120", f"got {dc['ref']!r}"
    # Point 4 — the counter moves to entered + 1, so 1..119 are never handed
    # out later.
    assert int(SET.dc_series()["next_no"]) == 121
    assert DN.highest_used(DN.DC, "") == 120


def test_the_challan_number_is_refused_backwards(store, sched):
    SET.save_dc_series("", 55)
    r = _dc_post(store, sched, doc_no_seq="20")
    assert r.status_code == 200, "a refused form re-renders rather than saving"
    assert not STORE["delivery_challans"], "nothing may be written"
    assert int(SET.dc_series()["next_no"]) == 55, "and the counter may not move"
    assert "0020" in r.get_data(as_text=True)


def test_a_challan_number_is_logged_as_an_override_and_never_printed(store, sched):
    _dc_post(store, sched, doc_no_seq="120")
    dc = next(iter(STORE["delivery_challans"].values()))
    trail = dc["number_override"]
    assert trail["from"] == "1" and trail["to"] == "120"
    assert trail["by"] and trail["by"] in STORE["users"], (
        "the trail carries a USER ID, not a display name (gap 41)")
    assert trail["at"]
    sheet = store.get(f"/dc/print/{dc['id']}").get_data(as_text=True)
    assert "120" in sheet, "the NUMBER prints"
    assert "number_override" not in sheet and trail["by"] not in sheet, (
        "the TRAIL does not")


def test_keeping_the_default_writes_no_override_trail(store, sched):
    _dc_post(store, sched, doc_no_seq="1")
    dc = next(iter(STORE["delivery_challans"].values()))
    assert "number_override" not in dc


def test_a_role_without_the_permission_cannot_change_a_challan_number(store, sched):
    """Purchase Manager holds `dc.create` and not `docnum.override`."""
    assert "dc.create" in auth.BUILTIN_ROLES["purchase-manager"][1]
    assert "docnum.override" not in auth.BUILTIN_ROLES["purchase-manager"][1]
    _sign_in_as(store, "purchase-manager")

    html = store.get(f"/dc/create?boq={sched}").get_data(as_text=True)
    assert "readonly" in html.split('name="doc_no_seq"')[1][:200]

    r = _dc_post(store, sched, doc_no_seq="120")
    assert r.status_code == 200 and not STORE["delivery_challans"]
    assert "permission" in r.get_data(as_text=True)

    # …and the default still saves for them.
    r = _dc_post(store, sched, doc_no_seq="1")
    assert r.status_code in (302, 303)
    assert next(iter(STORE["delivery_challans"].values()))["ref"] == "1"


# ── the tax invoice, through a proforma ────────────────────────────────────

@pytest.fixture()
def pi(store):
    """One proforma, written straight into the store."""
    STORE["proformas"]["p1"] = {
        "id": "p1", "ref": "PI-0001", "date": "2026-08-20",
        "account_name": "A Customer", "to": "A Customer\nPune",
        "line_items": [{"name": "Pipe", "qty": 1, "rate": 100.0, "total": 100.0,
                        "unit": "Nos", "hsn": "7306"}],
        "subtotal": 100.0, "grand_total": 118.0, "total_qty": 1,
        "tax_type": "cgst_sgst", "tax_info": {"total": 18.0},
    }
    return STORE["proformas"]["p1"]


def _ti_post(client, **extra):
    form = {"date": "2026-08-20", "place_of_supply": "Maharashtra",
            "advance_received": "0"}
    form.update(extra)
    return client.post("/invoice/from/p1", data=form)


def test_the_tax_invoice_form_prefills_and_splits_the_number(store, pi):
    html = store.get("/invoice/from/p1").get_data(as_text=True)
    assert 'class="dnum-fixed">SF/TI/26-27/</span>' in html, (
        "the prefix and the FY are TEXT, so they cannot be posted")
    assert 'name="doc_no_seq"' in html and 'value="0001"' in html


def test_an_RA_tax_invoice_ref_at_0007_blocks_a_TI_override_to_0007(store, pi):
    """⚠ The brief's named case, end to end and through the routes."""
    STORE["ra_bills"]["r1"] = {"id": "r1", "fy": FY, "ref": "SF/RA/26-27/0001",
                               "tax_invoice_ref": "SF/RI/26-27/0007"}
    r = _ti_post(store, doc_no_seq="7")
    assert r.status_code == 200 and not STORE["invoices"]
    assert "0007" in r.get_data(as_text=True)

    # …and to 0005, below the highest.
    r = _ti_post(store, doc_no_seq="5")
    assert r.status_code == 200 and not STORE["invoices"]
    body = r.get_data(as_text=True)
    assert "0005" in body and "0007" in body

    # 0008 goes through.
    r = _ti_post(store, doc_no_seq="8")
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    assert next(iter(STORE["invoices"].values()))["ref"] == "SF/TI/26-27/0008"


def test_the_tax_invoice_counter_advances_past_a_typed_number(store, pi):
    _ti_post(store, doc_no_seq="50")
    assert SER.next_seq("TI", FY) == 51, "max+1 over the record just written"
    assert DN.highest_used(DN.TI, FY) == 50


def test_the_skip_note_is_on_the_TI_form_and_on_no_other(store, pi, sched):
    """
    Point 6 — and the TI only. A gap in a tax invoice series shows in the
    *documents issued* table of a GSTR-1; a gap in a challan does not.
    """
    ti = store.get("/invoice/from/p1").get_data(as_text=True)
    assert "GSTR&#8209;1" in ti
    assert 'id="doc_no_seq_warn"' in ti, "the note's own element"

    # ⚠ The STYLESHEET is shared and is on every form that draws the field —
    #   `.dnum-warn` is in `DN.NUMBER_STYLES`, which is why this looks for the
    #   element the note is, not the class it would be styled by.
    dc = store.get(f"/dc/create?boq={sched}").get_data(as_text=True)
    assert 'id="doc_no_seq_warn"' not in dc
    assert "GSTR&#8209;1" not in dc


def test_a_tax_invoice_number_is_immutable_once_raised(store, pi):
    """
    ⚠ **A tax invoice has NO unissued state** — `invoice.py` gives it no
    draft, and its only later status is `cancelled`. So the number is settable
    at create and never again, and there is no route that offers it.
    """
    _ti_post(store, doc_no_seq="50")
    tid = next(iter(STORE["invoices"]))
    html = store.get(f"/invoice/view/{tid}").get_data(as_text=True)
    assert 'name="doc_no_seq"' not in html
    assert "/invoice/edit" not in html


# ── the proforma and the purchase order ────────────────────────────────────

def test_the_proforma_number_moves_forward_only(store):
    STORE["quotations"]["q1"] = {
        "id": "q1", "ref": "QT-0001", "date": "2026-08-01",
        "account_name": "A Customer", "to": "A Customer\nPune",
        "line_items": [{"name": "Pipe", "qty": 1, "rate": 100.0,
                        "total": 100.0, "unit": "Nos", "hsn": "7306"}],
        "subtotal": 100.0, "grand_total": 118.0, "total_qty": 1,
        "tax_type": "cgst_sgst", "tax_info": {"total": 18.0},
    }
    form = {"date": "2026-08-20", "advance_pct": "100", "validity_days": "15"}

    r = store.post("/proforma/from/q1", data={**form, "doc_no_seq": "30"})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    assert next(iter(STORE["proformas"].values()))["ref"] == "PI-0030"

    r = store.post("/proforma/from/q1", data={**form, "doc_no_seq": "30"})
    assert r.status_code == 200, "the same number a second time is refused"
    assert len(STORE["proformas"]) == 1


def test_a_DRAFT_purchase_order_number_is_editable_and_an_ISSUED_one_is_not(store):
    """
    ⚠ **The PO is the one of the four with a genuine unissued state.**
    `PO_STATUSES` defines `Draft` as "written, not yet sent to the vendor".
    """
    for status, drawn in (("Draft", True), ("Issued", False)):
        pid = f"po-{status}"
        STORE["purchases"][pid] = {
            "id": pid, "ref": f"SF/PO/26-27/000{1 if drawn else 2}",
            "fy": FY, "date": "2026-08-20", "status": status,
            "vendor_name": "A Vendor", "to": "A Vendor\nPune",
            "line_items": [{"name": "Pipe", "qty": 1, "price": 100.0,
                            "total": 100.0, "unit": "Nos", "discount_pct": 0}],
            "subtotal": 100.0, "grand_total": 100.0, "total_qty": 1,
            "tax_type": "exempt", "tax_info": {"total": 0.0},
        }
        html = store.get(f"/purchase/edit/{pid}").get_data(as_text=True)
        assert ('name="doc_no_seq"' in html) is drawn, (
            f"a {status} order: the number field should "
            f"{'be' if drawn else 'not be'} on the reprice form")


def test_an_issued_purchase_order_refuses_a_posted_number(store):
    """The server half: the field is absent, and a hand-made POST is refused."""
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": "SF/PO/26-27/0002", "fy": FY, "date": "2026-08-20",
        "status": "Issued", "vendor_name": "A Vendor", "to": "A Vendor\nPune",
        "line_items": [{"name": "Pipe", "qty": 1, "price": 100.0,
                        "total": 100.0, "unit": "Nos", "discount_pct": 0}],
        "subtotal": 100.0, "grand_total": 100.0, "total_qty": 1,
        "tax_type": "exempt", "tax_info": {"total": 0.0},
    }
    r = store.post("/purchase/edit/po1", data={
        "doc_no_seq": "900", "line_make": "", "line_rate": "100",
        "line_discount": "0", "note": ""})
    assert STORE["purchases"]["po1"]["ref"] == "SF/PO/26-27/0002", (
        "an Issued order's number is immutable")
    assert r.status_code == 200 and "permission" in r.get_data(as_text=True)


# ⚠ These three were added because the mutation run SURVIVED without them:
#   `/purchase/create` and the two upstream PO routes had no route test at all
#   (M21, M23), and nothing read the ledger back after a save (M20).

VENDOR_ID = "b2000006-face-4000-8000-000000000006"   # the seeded vendor


def test_the_purchase_create_route_takes_a_typed_number(store):
    from product import ensure_demo_products

    store.get("/address/")
    ensure_demo_products()
    r = store.post("/purchase/create", data={
        "date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "exempt", "doc_no_seq": "64",
        "line_product_id": [next(iter(STORE["products"]))],
        "line_qty": ["4"], "line_rate": ["750"]})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    po = next(iter(STORE["purchases"].values()))
    assert po["ref"] == "SF/PO/26-27/0064"
    assert po["number_override"]["from"] == "SF/PO/26-27/0001"
    assert DN.highest_used(DN.PO, FY) == 64
    assert SER.next_seq("PO", FY) == 65


def test_the_purchase_from_boq_route_takes_a_typed_number_in_the_right_year(store, sched):
    """
    ⚠ The financial year comes from the ORDER'S OWN DATE, so a back-dated
    order files against the year it belongs to. A mutation scanning the wrong
    scope survived until this existed.
    """
    import boq as BQ

    store.get("/address/")
    lines = STORE["boqs"][sched]["line_items"]
    heads = BQ.header_of(lines)
    first = min(heads)
    kid = [lines[i] for i in sorted(heads) if heads[i] == heads[first]][0]

    # A number already spent in THIS financial year, and none in any other.
    DN.note_used(DN.PO, FY, 40)
    r = store.post(f"/purchase/from-boq/{sched}", data={
        "date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "doc_no_seq": "40",
        "po_json": json.dumps({"lines": [{"line_id": kid["line_id"],
                                          "qty": "2", "rate": "100"}]})})
    assert r.status_code == 200, "0040 is already spent in 26-27"
    assert not STORE["purchases"]
    assert "0040" in r.get_data(as_text=True)

    r = store.post(f"/purchase/from-boq/{sched}", data={
        "date": "2026-08-16", "vendor_id": VENDOR_ID, "status": "Draft",
        "tax_type": "exempt", "cgst_rate": "9", "igst_rate": "18",
        "doc_no_seq": "41",
        "po_json": json.dumps({"lines": [{"line_id": kid["line_id"],
                                          "qty": "2", "rate": "100"}]})})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    assert next(iter(STORE["purchases"].values()))["ref"] == "SF/PO/26-27/0041"


def test_every_save_raises_the_LEDGER_even_when_the_number_was_automatic(store, pi):
    """
    ⚠ **The ledger is written on EVERY save, not only on an override.** It is
    the only one of the three readings that outlives a deleted record, so a
    save that skipped it would leave a number reusable the moment the document
    went. A mutation removing `note_used()` survived until this existed — for
    the tax invoice the scan covers it while the record is there, and a tax
    invoice is never deleted, which is exactly the reasoning that would have
    let the call be dropped by somebody tidying up.
    """
    _ti_post(store)      # no doc_no_seq at all: the automatic number
    assert DN.highwater()["TI"][FY] == 1
    _ti_post(store, doc_no_seq="9")
    assert DN.highwater()["TI"][FY] == 9


def test_a_draft_purchase_order_number_moves_and_is_logged(store):
    STORE["purchases"]["po1"] = {
        "id": "po1", "ref": "SF/PO/26-27/0001", "fy": FY, "date": "2026-08-20",
        "status": "Draft", "vendor_name": "A Vendor", "to": "A Vendor\nPune",
        "line_items": [{"name": "Pipe", "qty": 1, "price": 100.0,
                        "total": 100.0, "unit": "Nos", "discount_pct": 0}],
        "subtotal": 100.0, "grand_total": 100.0, "total_qty": 1,
        "tax_type": "exempt", "tax_info": {"total": 0.0},
    }
    r = store.post("/purchase/edit/po1", data={
        "doc_no_seq": "77", "line_make": "", "line_rate": "100",
        "line_discount": "0", "note": ""})
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:1500]
    po = STORE["purchases"]["po1"]
    assert po["ref"] == "SF/PO/26-27/0077"
    assert po["number_override"]["from"] == "SF/PO/26-27/0001"
    assert po["number_override"]["to"] == "SF/PO/26-27/0077"
    assert DN.highest_used(DN.PO, FY) == 77


# ═══════════════════════════════════════════════════════════════════════════
# 4. THE LEAF STAYS A LEAF
# ═══════════════════════════════════════════════════════════════════════════

def test_docnum_imports_neither_ra_nor_invoice():
    """
    ⚠ **The standing rule, and the whole reason the cross-collection scan is
    here.** `tests/test_import_directions.py` holds the full table; this is
    the one line of it this file is about, asserted where a reader of this
    file will look for it.
    """
    from tests.test_import_directions import imports_of  # noqa: PLC0415

    for banned in ("ra", "invoice", "merged_ra", "proforma", "purchase",
                   "challan", "settings", "auth", "flask"):
        assert banned not in imports_of("docnum"), (
            f"docnum.py imports {banned}; it is a leaf")
