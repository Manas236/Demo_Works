"""
The SCREEN pages, pinned byte-for-byte — committed BEFORE the chrome moves.

`tests/test_print_golden.py` pins the printed documents and one form. Nothing
pinned the ordinary screen pages — the registers, the settings form, the user
list, the dashboard itself — so a change to the shared chrome those pages all
render (`dashboard.BASE_STYLES`, `dashboard._nav()`) was measurable on the one
form the print file happens to hash and on nothing else.

Two changes to that chrome follow this file, and this file is what makes each
of them a measurement rather than a hope:

1. **The extraction** — `BASE_STYLES`, `_nav()` and everything nav-only move
   out of `dashboard.py` into a leaf, `chrome.py`, and every module that
   reached into `dashboard.py` for them imports the leaf instead. That is a
   refactor, and a refactor that moves a single rendered byte is not one:
   **every digest below must be byte-identical across it.** The order is the
   one that made the `docsheet.py` and `boqpick.py` extractions safe — the
   baseline is committed first, against the code as it stands, so a digest
   taken here is an observation and not a description of the result.

2. **The sidebar** — the chrome is redrawn. Every page here is expected to
   move, and the per-block digests are what say *where*: `head` and `main`
   must hold still on every page but the dashboard while `chrome` moves,
   because a redesign of the navigation has no business touching a register's
   table. That re-baseline happens in that commit and only there.

### The shape

Each page is rendered from a **fixed** store — fixed ids, fixed dates, fixed
figures, a fixed signed-in user, today's date pinned — and hashed whole
(sha256) and in three blocks split on the markers every screen page carries:

    head    <head>  …  up to the nav        the stylesheet stack
    chrome  <nav    …  up to <main          what _nav() emits
    main    <main   …  end of the page       the page's own body

`_blocks()` and `_sha()` are the print file's own, imported rather than
copied, so the two files cannot disagree about what a block digest is.

### Re-deriving these numbers

Literals, not computed — regenerating them from the code under test would
make the file assert that the code equals itself. When a change is intended,
run the suite, read the digest out of the failure, paste it in **in the same
commit as the change**, and say in the commit body which block moved and why.
"""

from datetime import date as _real_date

import pytest

import auth
import branding as B
import settings as settings_mod
from store import STORE
from test_print_golden import (  # noqa: F401  (fixtures are used by pytest)
    _blocks, _sha,
    pinned_identity, golden, golden_ra, golden_dc, golden_dpo, golden_merged,
    golden_ms, golden_picker,
    GOLD_TI, GOLD_PI, GOLD_PO, GOLD_DC, GOLD_DPO, GOLD_MERGED, GOLD_MS,
    GOLD_PICK_BOQ,
)


# ── The markers every screen page carries ──────────────────────────────────
#
# `<nav` and `<main` without their closing bracket, so the same marker finds
# `<nav>` today and a `<nav class="…">` tomorrow: the point of the split is to
# survive the redesign and report which side of it a change landed on.
PAGE_BLOCKS = [
    ("head",   "<head>"),
    ("chrome", "<nav"),
    ("main",   "<main"),
]

GOLD_USER = "gold-owner"
GOLD_PROJECT = "gold-project"
GOLD_PROJECT_2 = "gold-project-2"
GOLD_SITE = "gold-site-addr"
GOLD_EMP = "gold-emp-1"
GOLD_EMP_2 = "gold-emp-2"
GOLD_RCPT = "gold-receipt"
GOLD_CHARGE = "gold-charge"
GOLD_DATE = "2026-08-16"


class _FixedToday(_real_date):
    """
    `datetime.date` with today nailed down. A subclass rather than a stand-in,
    because `dashboard._metrics()` also CONSTRUCTS dates (`date(y, m, 1)` for
    the month axis) through the same name it calls `today()` on.
    """

    @classmethod
    def today(cls):
        return cls(2026, 8, 16)


@pytest.fixture()
def world(client, monkeypatch, pinned_identity, golden, golden_ra, golden_dc,
          golden_dpo, golden_merged, golden_ms):
    """
    Every collection a screen page reads, held still.

    The document collections come from the print goldens' own fixtures, so the
    registers list exactly the records the printed sheets are pinned on. The
    rest — users, roles, settings, addresses, projects, employees, markings,
    charges, receipts, the draft-PO and challan series — are snapshotted,
    replaced with fixed records, and put back afterwards, because
    `conftest.client` deliberately does not clear them between tests and a
    golden cannot hash whatever the previous test left behind.

    Two things a page reads that are not records: **today**, which the
    dashboard prints and buckets by, is pinned through `dashboard.date`; and
    **the signed-in user**, whose id is minted from `uuid4()` by
    `auth.create_user()` and would otherwise change the `/users` page's hrefs
    from one process to the next, is replaced by a fixed one and the session
    repointed at it.
    """
    import address
    import dashboard

    monkeypatch.setattr(dashboard, "date", _FixedToday)

    saved = {k: dict(STORE.get(k) or {}) for k in (
        "users", "roles", "settings", "addresses", "projects", "employees",
        "attendance", "charges", "receipts")}
    saved_flags = {k: STORE.get(k) for k in ("_addr_seeded", "_seeded")}

    # ── identity: one fixed Owner, and the session pointed at it ──────────
    STORE["users"].clear()
    STORE["users"][GOLD_USER] = {
        "id": GOLD_USER, "username": "test-owner", "display_name": "Test Owner",
        "password_hash": "not-a-hash", "role_ids": ["role-owner"],
        "active": True, "created_at": "2026-08-01 09:00", "created_by": "conftest",
    }
    STORE["roles"].clear()
    auth.ensure_builtin_roles()
    with client.session_transaction() as session:
        session[auth.SESSION_KEY] = GOLD_USER

    # ── settings: the specimen company only; every series at its default ──
    STORE["settings"].clear()
    STORE["settings"][settings_mod.RECORD_ID] = dict(settings_mod.DEMO_COMPANY)
    B.apply_settings(settings_mod.load_saved())

    # ── the address book: the six demo entries, re-seeded from scratch ────
    STORE["addresses"].clear()
    STORE["_addr_seeded"] = False
    address.ensure_demo_addresses()
    STORE["addresses"][GOLD_SITE] = {
        "id": GOLD_SITE, "label": "Whitefield site", "type": "site",
        "contact_name": "R. Kadam", "company": "Sify Infinit",
        "line1": "Survey 21", "line2": "", "landmark": "", "city": "Bangalore",
        "state": "Karnataka", "pincode": "560066", "country": "India",
        "phone": "", "email": "", "gstin": "",
    }

    # ── projects ──────────────────────────────────────────────────────────
    STORE["projects"].clear()
    STORE["projects"][GOLD_PROJECT] = {
        "id": GOLD_PROJECT, "name": "Sify Bangalore — Fire Protection",
        "norm_name": "sify bangalore — fire protection",
        "client": "Prudent Teqtis Pvt Ltd", "notes": "",
        "site_address_id": GOLD_SITE, "site_address": "Whitefield site",
        "created_at": "2026-04-01 10:00", "updated_at": "2026-04-01 10:00",
    }
    STORE["projects"][GOLD_PROJECT_2] = {
        "id": GOLD_PROJECT_2, "name": "Kohinoor Techpark — Hydrant",
        "norm_name": "kohinoor techpark — hydrant",
        "client": "Kohinoor Techpark Pvt. Ltd.", "notes": "Phase 2 tender",
        "site_address_id": "", "site_address": "",
        "created_at": "2026-05-12 15:30", "updated_at": "2026-05-12 15:30",
    }
    STORE["boqs"]["gold-boq"]["project_id"] = GOLD_PROJECT

    # ── employees and two markings on the pinned day ──────────────────────
    STORE["employees"].clear()
    STORE["employees"][GOLD_EMP] = {
        "id": GOLD_EMP, "name": "Ramesh Patil", "code": "SF-014",
        "designation": "Fitter", "site": "Whitefield site",
        "site_address_id": GOLD_SITE, "site_source": "book",
        "date_joined": "2026-04-01", "day_rate": 1200.0, "active": True,
        "notes": "", "created_at": "2026-04-01 10:00", "updated_at": "2026-04-01 10:00",
    }
    STORE["employees"][GOLD_EMP_2] = {
        "id": GOLD_EMP_2, "name": "Suresh Naik", "code": "SF-015",
        "designation": "Helper", "site": "Whitefield site",
        "site_address_id": GOLD_SITE, "site_source": "book",
        "date_joined": "2026-05-01", "day_rate": 800.0, "active": True,
        "notes": "", "created_at": "2026-05-01 10:00", "updated_at": "2026-05-01 10:00",
    }
    STORE["attendance"].clear()
    STORE["attendance"]["gold-att-1"] = {
        "id": "gold-att-1", "date": GOLD_DATE, "employee_id": GOLD_EMP,
        "employee_name": "Ramesh Patil", "employee_code": "SF-014",
        "day_rate": 1200.0, "site": "Whitefield site", "site_address_id": GOLD_SITE,
        "site_source": "book", "project_id": GOLD_PROJECT,
        "project_name": "Sify Bangalore — Fire Protection",
        "status": "present", "ot_hours": 2.0, "notes": "",
        "created_at": "2026-08-16 18:00", "updated_at": "2026-08-16 18:00",
    }
    STORE["attendance"]["gold-att-2"] = {
        "id": "gold-att-2", "date": GOLD_DATE, "employee_id": GOLD_EMP_2,
        "employee_name": "Suresh Naik", "employee_code": "SF-015",
        "day_rate": 800.0, "site": "Whitefield site", "site_address_id": GOLD_SITE,
        "site_source": "book", "project_id": GOLD_PROJECT,
        "project_name": "Sify Bangalore — Fire Protection",
        "status": "absent", "ot_hours": 0.0, "notes": "",
        "created_at": "2026-08-16 18:00", "updated_at": "2026-08-16 18:00",
    }

    # ── a charge and a receipt ────────────────────────────────────────────
    STORE["charges"].clear()
    STORE["charges"][GOLD_CHARGE] = {
        "id": GOLD_CHARGE, "date": "2026-08-10", "person": "R. Kadam",
        "head": "Travel", "description": "Site visit, Whitefield",
        "project_id": GOLD_PROJECT, "project_name": "Sify Bangalore — Fire Protection",
        "taxable_amount": 1200.0, "gst_rate": 0.0, "gst_amount": 0.0,
        "total": 1200.0, "notes": "",
        "created_at": "2026-08-10 19:00", "updated_at": "2026-08-10 19:00",
        "approval_status": "approved",
    }
    STORE["receipts"].clear()
    STORE["receipts"][GOLD_RCPT] = {
        "id": GOLD_RCPT, "ref": "SF/RCPT/26-27/0001", "fy": "26-27",
        "date": "2026-06-20", "ra_id": "gold-ra", "ra_ref": "SF/RA/26-27/0002",
        "ra_no": 2, "leg": "supply", "boq_id": "gold-boq",
        "boq_ref": "SF/BOQ/26-27/0001",
        "project_name": "Sify Bangalore — Fire Protection",
        "account_name": "Prudent Teqtis Pvt Ltd",
        "amount": 100000.0, "write_off": 0.0, "mode": "neft",
        "instrument_ref": "UTR20260620", "instrument_date": "2026-06-19", "notes": "",
    }

    yield

    for k, v in saved.items():
        STORE[k].clear()
        STORE[k].update(v)
    for k, v in saved_flags.items():
        STORE[k] = v
    B.apply_settings(settings_mod.load_saved())


def _check(html: str, expect_whole: str, expect_len: int, expect_blocks: dict,
           what: str):
    got_len, got_whole = len(html), _sha(html)
    if got_whole != expect_whole:
        got_blocks = _blocks(html, PAGE_BLOCKS)
        moved = [n for n in expect_blocks if got_blocks[n] != expect_blocks[n]]
        assert not moved, (
            f"{what}: these blocks changed — {moved}. "
            f"Expected {expect_blocks}, got {got_blocks}. "
            f"Whole page {expect_whole} -> {got_whole}, "
            f"{expect_len} -> {got_len} bytes.")
    assert (got_whole, got_len) == (expect_whole, expect_len), (
        f"{what}: the rendered page changed. "
        f"sha {expect_whole} -> {got_whole}, bytes {expect_len} -> {got_len}. "
        f"Every block hashed the same, so the difference is outside them — "
        f"before <head>, or between two markers.")


# ── The pages, one per blueprint that renders the app chrome ───────────────
#
# Captured 14 September 2026, against the code as it stood BEFORE `chrome.py`
# existed. `/product/` is absent because the catalogue is hidden from
# everybody (auth.HIDDEN_BLUEPRINTS) and the route answers 403; `/login` and
# `/setup` render no chrome by design; the `approval` blueprint's routes are
# refused while the ladder is off. Everything else that draws `_nav()` is here.
PAGES = {
    # (name, url): (whole sha, byte length, {block: sha})
    ("dashboard",       "/"):                          ("95cef7e806e76ebb", 75527,
        {"head": "82ccf616ed396130", "chrome": "da45a50ca5a64535", "main": "6f7ab23be07cd879"}),
    ("quotations",      "/quotation/"):                ("7a369fe5f706ed75", 45737,
        {"head": "e97b6494b3902a0c", "chrome": "2cd225a442c6338d", "main": "7ec3c661ae9cc372"}),
    ("proformas",       "/proforma/"):                 ("9894c6661b2e29c3", 51233,
        {"head": "ecfb0bb956a7f1e4", "chrome": "2cd225a442c6338d", "main": "99ac6790fecd3140"}),
    ("tax invoices",    "/invoice/"):                  ("e71d1a08911af4bb", 58140,
        {"head": "907de192a97c19e7", "chrome": "2cd225a442c6338d", "main": "9acd0372dd4402aa"}),
    ("purchase orders", "/purchase/"):                 ("5d2a63f96585b9ae", 55303,
        {"head": "41f700a498f09c12", "chrome": "2cd225a442c6338d", "main": "80dfa73ee439cc3e"}),
    ("spec library",    "/spec/"):                     ("a109ad85f172fd60", 73623,
        {"head": "da7e18e4077bdbf5", "chrome": "2cd225a442c6338d", "main": "ffab9c68d1fb9d41"}),
    ("BOQs",            "/boq/"):                      ("c83998bff52b2c9c", 62509,
        {"head": "915ac3127da8e793", "chrome": "2cd225a442c6338d", "main": "413eaba106b25ef1"}),
    ("RA bills",        "/ra/"):                       ("59aca7519c67ced7", 69731,
        {"head": "2c8238a8f19c0d28", "chrome": "2cd225a442c6338d", "main": "148536cc5ea624cc"}),
    ("merged RAs",      "/merged/"):                   ("ea8f559828f73add", 62269,
        {"head": "fa47c4e53e7a731f", "chrome": "c59ddab4c4308401", "main": "16cffd227809676f"}),
    ("receipts",        "/receipt/"):                  ("e86f3b47fbf55895", 61518,
        {"head": "6a53f8c74fdbe478", "chrome": "c59ddab4c4308401", "main": "3fe4fb4699344259"}),
    ("clients",         "/client/"):                   ("6a3e2d773bd11656", 47568,
        {"head": "1e3f64d1fee60778", "chrome": "c59ddab4c4308401", "main": "9e3d19393d21eae4"}),
    ("draft POs",       "/po/"):                       ("2907462f309cca75", 46296,
        {"head": "586c5dde500683f0", "chrome": "c59ddab4c4308401", "main": "82ba49a010dd9872"}),
    ("challans",        "/dc/"):                       ("3de2d83a559ff4dc", 51432,
        {"head": "e2fef1b330f5cacd", "chrome": "c59ddab4c4308401", "main": "30651a1c7dcacad9"}),
    ("measurements",    "/measurement/"):              ("93d8f41818e57292", 44035,
        {"head": "ac59fe4b7d58ffcd", "chrome": "c59ddab4c4308401", "main": "357bd0902a7b8770"}),
    ("projects",        "/projects/"):                 ("e4b6b54188fc09f7", 24456,
        {"head": "ccdd5748cffa1046", "chrome": "da45a50ca5a64535", "main": "b61a7f3ca9178c9b"}),
    ("project page",    f"/projects/view/{GOLD_PROJECT}"): ("23712fbf9ff4b2a7", 51871,
        {"head": "a79fa7c98fc28dff", "chrome": "e3ced8a9d1568a98", "main": "85908eff05b3e868"}),
    ("employees",       "/employee/"):                 ("a724f409acedba31", 41274,
        {"head": "d3e6d4ea8d13c091", "chrome": "c59ddab4c4308401", "main": "14f4d8921e680fc4"}),
    ("attendance",      f"/attendance/?date={GOLD_DATE}"): ("c3576cd950e234dd", 47634,
        {"head": "64182c5b7ca8f13e", "chrome": "c59ddab4c4308401", "main": "bb8159e0b0291642"}),
    ("charges",         "/charge/"):                   ("993ab8d61c40e5c3", 40901,
        {"head": "20ca83f1acd7476b", "chrome": "c59ddab4c4308401", "main": "daf605a8f367bb3e"}),
    ("address book",    "/address/"):                  ("3e244b60f80be2f2", 50564,
        {"head": "cf5a57456c7f2d38", "chrome": "da45a50ca5a64535", "main": "7e67e775827dc7af"}),
    ("settings",        "/settings/"):                 ("51cd28aa5a750a53", 49668,
        {"head": "dcf782c1620f224f", "chrome": "2cd225a442c6338d", "main": "741824ea93f3b3cb"}),
    ("users",           "/users"):                     ("9f6954438e49480e", 40406,
        {"head": "24a4c49170999e75", "chrome": "c59ddab4c4308401", "main": "645012baa0685fdd"}),
}


@pytest.mark.parametrize("name,url", list(PAGES), ids=[n for n, _u in PAGES])
def test_the_screen_page_is_unchanged(name, url, client, world):
    r = client.get(url)
    assert r.status_code == 200, f"{name}: {url} -> {r.status_code}"
    whole, length, blocks = PAGES[(name, url)]
    _check(r.get_data(as_text=True), whole, length, blocks, what=name)


def test_the_page_goldens_are_hashing_real_pages(client, world):
    """
    The control. A digest passes just as well against a refusal page, an empty
    register or a store that silently stopped seeding, so each page is checked
    for the thing it claims to show before any digest is believed.
    """
    get = lambda u: client.get(u).get_data(as_text=True)  # noqa: E731

    home = get("/")
    assert "Sunday, 16 August 2026" in home, "today is not pinned on the dashboard"
    assert "Test Owner" in home, "the fixed user is not the one signed in"
    assert "QT-0001" in home, "the golden quotation is not on the dashboard"

    assert "SF/BOQ/26-27/0001" in get("/boq/"), "the golden BOQ is not listed"
    assert "SF/RA/26-27/0002" in get("/ra/"), "the golden RA bill is not listed"
    assert "SF/RCPT/26-27/0001" in get("/receipt/"), "the receipt is not listed"
    assert "SF/DPO/0007" in get("/po/"), "the golden draft PO is not listed"
    assert "Open delivery challan 54" in get("/dc/"), "the golden challan is not listed"
    assert "SF/MS/26-27/0007" in get("/measurement/"), "the joint sheet is not listed"
    assert "SF/MI/26-27/0001" in get("/merged/"), "the merged document is not listed"
    assert "SF/PO/26-27/0001" in get("/purchase/"), "the golden PO is not listed"
    assert "SF/TI/26-27/0001" in get("/invoice/"), "the golden TI is not listed"
    assert "PI-0001" in get("/proforma/"), "the golden PI is not listed"
    assert "Kohinoor Techpark" in get("/projects/"), "the projects are not listed"
    assert "Ramesh Patil" in get("/employee/"), "the employees are not listed"
    assert "SF-015" in get(f"/attendance/?date={GOLD_DATE}"), "the muster is empty"
    assert "Site visit, Whitefield" in get("/charge/"), "the charge is not listed"
    assert "Whitefield site" in get("/address/"), "the address book is not listed"
    assert "Prudent Teqtis" in get("/client/"), "the client register is empty"
    assert "2026-08-01 09:00" in get("/users"), "the fixed user's row is missing"
    assert "SPECIMEN BANK" in get("/settings/"), "the pinned identity is not loaded"


def test_every_pinned_page_renders_the_shared_chrome(client, world):
    """
    The shape the split relies on: every page here carries a `<nav` and a
    `<main`, in that order, after its `<head>`. A page that lost either has
    lost the chrome this file exists to measure.
    """
    for (name, url) in PAGES:
        html = client.get(url).get_data(as_text=True)
        cuts = [html.find(m) for _n, m in PAGE_BLOCKS]
        assert all(c >= 0 for c in cuts), f"{name}: a marker is missing ({cuts})"
        assert cuts == sorted(cuts), f"{name}: the markers are out of order"
