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

   ✅ **Both measured, 14 September 2026.** Across the extraction all 22 pages
   were byte-identical (commit `efa3467`). Across the sidebar, **`main` is
   byte-identical on all 21 register pages** and moved on the dashboard only,
   where the module zones and the status chips ARE the content. The shell —
   the stylesheet and script `_nav()` now emits first, then the rail and the
   top bar — is what moved everywhere else. The pre-redesign three-block
   digests are in commit `52ad1f8` rather than repeated here; every `main`
   digest below is that commit's, unchanged, except the dashboard's.

### The shape

Each page is rendered from a **fixed** store — fixed ids, fixed dates, fixed
figures, a fixed signed-in user, today's date pinned — and hashed whole
(sha256) and in four blocks split on the markers every screen page carries:

    head    <head>  …  up to the shell      the page's <head> and <body> opening
    shell   the shell's <style> … up to <nav   chrome.CHROME_STYLES + CHROME_SCRIPT
    chrome  <nav    …  up to <main          the rail and the top stack
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
    golden_ms, golden_picker, pinned_counts,
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
    # ⚠ **A fourth block from the sidebar commit (14 September 2026).**
    #   `_nav()` now emits the shell's own stylesheet and script FIRST, in the
    #   body, before the rail — so a split at `<nav` alone put ~25 KB of chrome
    #   in the `head` block and reported every page's head as moved when no
    #   page's `<head>` element had changed. The shell is its own block now,
    #   from the first byte of `chrome.CHROME_STYLES` to the rail; `head` is
    #   the page's `<head>` element and its `<body>` opening, which is what it
    #   was always meant to hold.
    ("shell",  "<style>\n  :root {\n    --rail-w"),
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
    # ⚠ **RE-BASELINED 29 October 2026 — `shell` and `chrome` ONLY, on ALL 22
    #   pages, +0 bytes** (CLIENT_CHANGES.md §0 fifty-seventh block: the SF mark
    #   1.5x on screen). The rail's mark is drawn at 42 px (was 28) and the top
    #   bar's at 39 px (was 26): the two `logo_img()` calls sit in `chrome`, and
    #   the two CSS rules that size them sit in `shell`. Every page is exactly
    #   the length it was, because each number keeps its two digits.
    #
    #   Measured before the baseline was touched: each page rendered with the
    #   change and then with ONLY those four size strings put back (the two
    #   `<img>` width/height/style runs and the two CSS rules, each found
    #   exactly once per page) hashed to the OLD digests below exactly, whole
    #   and block for block. **4 lines changed per page and nothing else**;
    #   `head` and `main` did not move, and no print golden moved. The old
    #   `shell` digest, the same on every page, was "75cda0afbae27209"; the old
    #   whole and `chrome` digests:
    #       address book:    ("def4ca415fbc0f49", 75650, {..., "chrome": "35480409a092776b"})
    #       attendance:      ("4a7fcd42ceca4c19", 73298, {..., "chrome": "864f7a2ba55bb64a"})
    #       BOQs:            ("da65fd57390c41ea", 87604, {..., "chrome": "606ce55e81259faa"})
    #       challans:        ("4ddb960f86b83e82", 76341, {..., "chrome": "07b78e62d2bbf81c"})
    #       charges:         ("52eec3cf3cd7c8cd", 66001, {..., "chrome": "19250b6392869c12"})
    #       clients:         ("b539d6762348461b", 72469, {..., "chrome": "34843c9b79426c0a"})
    #       dashboard:       ("5aba0b01faac2349", 107435, {..., "chrome": "5c161e609be944c8"})
    #       draft POs:       ("fbbdae870b7c8492", 71208, {..., "chrome": "1da3a693f583e9cc"})
    #       employees:       ("fd7d40f31d63a52e", 66359, {..., "chrome": "8ad3f37192de4e4d"})
    #       measurements:    ("087142596310c260", 68945, {..., "chrome": "604e1a5956a90ace"})
    #       merged RAs:      ("c8c76cbaad9ecafa", 87366, {..., "chrome": "602a5f1ea1698609"})
    #       proformas:       ("7d76c8fa785a4097", 76141, {..., "chrome": "739e7979087b4d6a"})
    #       project page:    ("97b3a40f2d68e3e7", 85531, {..., "chrome": "b03da1368479ad8b"})
    #       projects:        ("2f4005ad31c9a322", 50009, {..., "chrome": "89e92c31f075ea28"})
    #       purchase orders: ("ddd6e71e5ba97679", 80408, {..., "chrome": "20aa8d813a8d7958"})
    #       quotations:      ("36d5f6af2d97f948", 70833, {..., "chrome": "b5fd1962d836d50d"})
    #       RA bills:        ("3a5536d4d6af4366", 94831, {..., "chrome": "55368f6b238833b4"})
    #       receipts:        ("c08e0ecf87251688", 87073, {..., "chrome": "3033c4bdc0669eaa"})
    #       settings:        ("e8ac29906e5c9ec0", 85011, {..., "chrome": "d107029c10eb2dec"})
    #       spec library:    ("f4df328387214170", 98711, {..., "chrome": "ac89f317bbc5800e"})
    #       tax invoices:    ("36c5d2c1be5c3e01", 84618, {..., "chrome": "e3e943b1df420c01"})
    #       users:           ("245cd030c38e595c", 65816, {..., "chrome": "907015465e3197ed"})
    # ⚠ **RE-BASELINED 29 October 2026 — the Draft PO is DISPLAYED as
    #   "Product Inquiry"** (CLIENT_CHANGES.md §0 **fifty-ninth** block, B1,
    #   from the 28 October 2026 meeting with Yogesh Bankar). **DISPLAY ONLY**:
    #   the module, the blueprint, `STORE["purchase_orders"]`, every `/po/`
    #   URL, every stored field and the `SF/DPO` series are untouched, and
    #   `tests/test_product_inquiry_name.py` asserts each one.
    #
    #   `chrome` moves on **all 22 pages** — the rail's link title and the top
    #   bar's name both read `chrome.REGISTERS`' label, and "Draft Purchase
    #   Orders" (21 characters) became "Product Inquiries" (17), which is
    #   **exactly the −8 bytes** 18 of the pages show. `shell` is
    #   byte-identical everywhere: no stylesheet moved. Four pages move a
    #   second block, and each is a place that prints the words:
    #     - **draft POs** — `head` (its `<title>`) and `main` (the `<h1>`, the
    #       register intro, the empty-register note and the footer): −24
    #     - **dashboard** — `main` (the card title): −12
    #     - **project page** — `main` (the P&L's *not counted, on purpose*
    #       sentence): −13
    #     - **settings** — `main` (the series section's heading, its three
    #       hints and the hand-typed-number paragraph's list): **+7**
    #
    #   **MEASURED, and proved by stripping.** 19 of the 22 pages recover the
    #   old digest EXACTLY when the six display constants
    #   (`po_draft.DOC_NAME` and friends), `chrome.REGISTERS`' label and the
    #   cascade edge's label are put back. The other three — draft POs,
    #   settings and the project page — also carry literals in `settings.py`
    #   and `projectview.py`, which cannot be monkeypatched, so they were
    #   proved the stronger way instead: each page was rendered at the commit
    #   before this one and diffed line by line against the page rendered
    #   after, and **every differing line is one of the renamed words and
    #   nothing else**. Same for `/po/print`. The old values:
    #       dashboard        ("0f2414f4f3d8a0e2", 109451)
    #       quotations       ("693c1f033c5472df", 70833)
    #       proformas        ("ec746a1c49227b83", 76141)
    #       tax invoices     ("e4e38336b84380e3", 84618)
    #       purchase orders  ("69f80a29bac0b502", 80408)
    #       spec library     ("6bf18e783e3a8ebe", 98711)
    #       BOQs             ("eb30f84b389b3d32", 87604)
    #       RA bills         ("47cf13aac2d2928f", 94831)
    #       merged RAs       ("f034b133e1645c9e", 87366)
    #       receipts         ("edb0a742f1f537b0", 87073)
    #       clients          ("da5879a14c5ec7e3", 72469)
    #       draft POs        ("9c22981be354f8db", 71208)
    #       challans         ("167062c7a3ada7b5", 76341)
    #       measurements     ("2d3ea7a519866828", 68945)
    #       projects         ("ea3228a536b47668", 50331)
    #       project page     ("db5530bdd8ec811e", 101798)
    #       employees        ("ef174191c4b15546", 66359)
    #       attendance       ("a480fef039a56a85", 73298)
    #       charges          ("0b4fe777d631ee90", 66001)
    #       address book     ("670d91c5c30aff7f", 75650)
    #       settings         ("9e64b879895952e9", 85011)
    #       users            ("21aa86c59889282b", 65816)
    # (name, url): (whole sha, byte length, {block: sha})
    #
    # ⚠ **RE-BASELINED 30 October 2026 — FIFTEEN registers, `head` and `main`
    #   ONLY, for the register table fit.** The owner opened the list pages and
    #   reported that the table runs out of its white card — on `/charges` the
    #   Edit/Delete pair stacked outside the row, the date broke across two
    #   lines and an empty Approval column held width. The cause is shared and
    #   not per-page: `quotation.QUOTATION_STYLES`, which nearly every screen
    #   page loads, styles tables through BARE ELEMENT selectors with 1.1rem of
    #   cell padding on each side — 2.2rem per column, which an eleven-column
    #   register cannot fit — and `.table-wrap` clips (`overflow:hidden`)
    #   rather than scrolling. `quotation.py` is FROZEN, so the answer is
    #   `chrome.TABLE_FIT_STYLES`: a screen-only constant loaded LAST in the
    #   head of a register page, overriding those rules from the cascade.
    #
    #   The fifteen that moved are exactly the registers that took it:
    #   proformas, tax invoices, purchase orders, spec library, BOQs, RA bills,
    #   merged RAs, receipts, clients, draft POs, measurements, projects,
    #   employees, charges, users. **+3,027 to +3,369 bytes each**, of which
    #   3,019 is the constant itself and the rest is the wrapper div and the
    #   class attributes on that page's own cells.
    #
    #   ⚠ **`shell` and `chrome` are byte-identical on all fifteen** — the
    #   stylesheet goes in the page's own `<head>`, never into `BASE_STYLES`
    #   (which five print goldens hash, and `USER_CHIP_STYLES` records why).
    #   **NO PRINT GOLDEN MOVED**: `tests/test_print_golden.py` is 66 passed,
    #   `/po/create` among them, because every rule is inside `@media screen`
    #   and `docsheet.py` never loads the constant.
    #
    #   ⚠ **Seven pinned pages did NOT move and that is the control**:
    #   dashboard, quotations (frozen), challans, attendance, project page,
    #   address book and settings. `/dc/` and `/attendance/` already carry
    #   `dashboard.py`'s register stylesheet from 30 August 2026 — this pass is
    #   that same remedy reaching the registers it was scoped away from.
    #
    #   Proved rather than asserted: every pinned page was rendered before and
    #   after the change, and once CSS, class attributes, `<div>` tags and
    #   whitespace are removed the two are character-identical on all 22 pages.
    #   No text, number, link or table cell changed.
    # ⚠ **RE-BASELINED 5 October 2026 — `main` ONLY**, for the Work Orders
    #   card (CLIENT_CHANGES.md §0 forty-first block). The brief allowed a nav
    #   entry only if it moved no golden; a `chrome.REGISTERS` entry moves the
    #   `chrome` block of every page here, so the brief's fallback — a
    #   dashboard card — was taken, and this is the one page it moves.
    #
    #   Measured before the baseline was touched: with `_work_orders_zone()`
    #   returning "", this page hashed to the OLD digest below exactly. So the
    #   whole difference is the zone itself — **+982 bytes, 0 bytes removed** —
    #   and `head` / `shell` / `chrome` did not move. The old values:
    #       ("5e225e0820d80885", 106453,
    #        {"head": "6dc069f834093b21", "shell": "75cda0afbae27209",
    #         "chrome": "5c161e609be944c8", "main": "2b2035d29d7ba0bd"})
    # ⚠ **RE-BASELINED 29 October 2026 — CLIENT_CHANGES.md §0's fifty-eighth
    #   block, item 4** (the profit and loss, one click away). THREE pages
    #   move and no others. Measured before any baseline was touched, by
    #   reverting `pnl.py`, `projectview.py`, `project.py` and `dashboard.py`
    #   and re-running this file plus `tests/test_pnl_access.py`: **all 42
    #   assertions came back green on the old values**, so nothing below moved
    #   for any other reason.
    #
    #   - **dashboard** — `head` AND `main`. `head` carries `DASH_STYLES`,
    #     which gains the `.pp-pnl` rules (the P&L pill on a project row);
    #     `main` gains the pill itself, one per project the reader may open.
    #     `shell` and `chrome` unmoved. **+569 bytes.**
    #   - **projects** — `main` only: a **P&L** button per register row
    #     (`project._pnl_link()`). `head` / `shell` / `chrome` unmoved.
    #     **+322 bytes.**
    #   - **project page** — `main` only: the panel gains *Planned margin
    #     against actual* with the **coverage** sentence, and the **cost
    #     tagged to no project** band. `head` / `shell` / `chrome` unmoved.
    #     **+1,014 bytes.**
    #
    #   Every one of the three is gated on `project.pnl`, which is why
    #   `tests/test_pnl_access.py` needed **no** re-baseline for this item:
    #   all four of its roles lack that permission and all eight of its rows
    #   are byte-identical.
    #   The old value:
    #       ("dashboard", "/"): ("4a9da9c12ffb2724", 107435,
    #        {"head": "6dc069f834093b21", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "6167869fb277a647", "main": "c7511bccc57b6167"})
    # ⚠ **RE-BASELINED AGAIN, same day — §0 fifty-eighth block, item 5** (the
    #   pictures). `head` AND `main` again: `head` carries `DASH_STYLES`,
    #   which gains the `.pp-mini*` and `.pp-margin` rules; `main` gains the
    #   compact per-project money row (two bars and the margin in words).
    #   `shell` and `chrome` unmoved. **+1,447 bytes.** The value before
    #   item 5:
    #       ("dashboard", "/"): ("eea710973601aeb5", 108004,
    #        {"head": "cbce33bfb1cb901f", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "6167869fb277a647", "main": "b5c4975fcffe0cbd"})
    # ⚠ **RE-BASELINED 31 October 2026 — `main` ONLY, +371 bytes**
    #   (CLIENT_CHANGES.md §0 sixty-third block, C5/C7): each project tile
    #   gains its *Running position* line with *billed N% of the contract
    #   value*, and the Unattributed cost line is drawn under the tiles for a
    #   `project.pnl` reader. `head`/`shell`/`chrome` unmoved. The old row:
    #       ("4ff0bc6a35ae7c9c", 109439, {..., "main": "9aed9013889622db"})
    ("dashboard",       "/"):                          ("855698a7b62a425d", 109810,
        {"head": "024abb845bc90f71", "shell": "a1e6c63a6d4c6ac2", "chrome": "98789be45a2abed2", "main": "3e9d91230374421e"}),   # §0 59th B1: moved=['chrome', 'main'], -12 bytes
    ("quotations",      "/quotation/"):                ("f7af9a508c3c8d73", 70825,
        {"head": "6a1ba8490f2cdcd0", "shell": "a1e6c63a6d4c6ac2", "chrome": "428580664f0626bf", "main": "7ec3c661ae9cc372"}),   # §0 59th B1: moved=['chrome'], -8 bytes
    ("proformas",       "/proforma/"):                 ("be95d64b9f9caa5d", 79225,
        {"head": "f1e920fa8474816f", "shell": "a1e6c63a6d4c6ac2", "chrome": "5acba1eef816bda5", "main": "d21f84af1fd212ea"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3092 bytes
    # was 838b42d5894c49c6 / 83043 / head 28aee5e42e857421 before the
    # 23 Sep 2026 cancellation overprint. ⚠ `head` ALONE moved (+1,575 bytes of
    # `.lc-*` rules in INVOICE_STYLES, which every page in this module loads);
    # `shell`, `chrome` and `main` are byte-identical, so the register itself
    # did not change at all.
    ("tax invoices",    "/invoice/"):                  ("501060301c132a52", 87735,
        {"head": "771b458ef7f6907b", "shell": "a1e6c63a6d4c6ac2", "chrome": "a49882780cc9c0b6", "main": "9d127c19134aafc8"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3125 bytes
    ("purchase orders", "/purchase/"):                 ("eaf76de4c0ae9820", 83532,
        {"head": "128a0b2465b764e2", "shell": "a1e6c63a6d4c6ac2", "chrome": "2902f3faeda11014", "main": "5352138b5dd7b785"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3132 bytes
    ("spec library",    "/spec/"):                     ("52a466ada96d21be", 102072,
        {"head": "1625ae0337df4d80", "shell": "a1e6c63a6d4c6ac2", "chrome": "da9e01d1dfe05971", "main": "ccf9720d9ae550d8"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3369 bytes
    ("BOQs",            "/boq/"):                      ("27d8f5d9c272d301", 90697,
        {"head": "22d784e89a251e85", "shell": "a1e6c63a6d4c6ac2", "chrome": "2e443224a6988db5", "main": "e7ad92369c430c30"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3101 bytes
    ("RA bills",        "/ra/"):                       ("cf6ba30ae6c8212a", 97988,
        {"head": "963a5a22a46d197e", "shell": "a1e6c63a6d4c6ac2", "chrome": "25a322f519fd2099", "main": "91a5c760a0a084fd"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3165 bytes
    ("merged RAs",      "/merged/"):                   ("3032d6948546d374", 90510,
        {"head": "c400449c890a2730", "shell": "a1e6c63a6d4c6ac2", "chrome": "7453600ea49c28f7", "main": "f13001168bcbcfa7"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3152 bytes
    # was 0507f0420f7839fd / 86611 / head 2cc6952bbfa08148 before the
    # 23 Sep 2026 delete rollout. ⚠ `head` ALONE moved (+462 bytes of
    # `cascade.CASCADE_STYLES`, loaded by receipt.py's shared `_shell()` so the
    # delete confirmation can draw its impact block); `shell`, `chrome` and
    # `main` are byte-identical, so the register itself did not change.
    ("receipts",        "/receipt/"):                  ("6159990512cabc77", 90092,
        {"head": "5dba095cb4b0893a", "shell": "a1e6c63a6d4c6ac2", "chrome": "3c4364586ec6edbd", "main": "3ac3f9c07d30187e"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3027 bytes
    ("clients",         "/client/"):                   ("ec3d07c8ad343590", 75553,
        {"head": "988fb2a12fb791bb", "shell": "a1e6c63a6d4c6ac2", "chrome": "8c53e352bfe5210d", "main": "6da1dc1aca0606c4"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3092 bytes
    ("draft POs",       "/po/"):                       ("8314ea723a0fdcc8", 74268,
        {"head": "ee075a3c146a36b3", "shell": "a1e6c63a6d4c6ac2", "chrome": "2188f23e97ff0ab1", "main": "9db6cea2e6477047"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3084 bytes
    ("challans",        "/dc/"):                       ("e6c7cbc444975fe1", 76333,
        {"head": "660a40e2abebd6f2", "shell": "a1e6c63a6d4c6ac2", "chrome": "1d76c188613d8d80", "main": "30651a1c7dcacad9"}),   # §0 59th B1: moved=['chrome'], -8 bytes
    ("measurements",    "/measurement/"):              ("f9e05bb4a913e6f8", 72046,
        {"head": "e07a8c7af120014b", "shell": "a1e6c63a6d4c6ac2", "chrome": "263eda7ebc35c9f7", "main": "689dfe3e81057d9f"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3109 bytes
    # ⚠ **RE-BASELINED 8 October 2026 — `main` ONLY, and for the OWNER ONLY**,
    #   for CC-2 C6 (CLIENT_CHANGES.md §0 forty-seventh block). This file signs
    #   in as `gold-owner`, who holds `project.pnl`; the register gains the
    #   "Cost not tagged to any project" line and the project page gains the
    #   Profit & Loss panel. Measured before the baseline was touched: with
    #   `project.pnl` withheld from the same Owner, both pages hashed to the OLD
    #   digests below exactly; and with the line (**+461 bytes**) and the panel
    #   (**+6,368 bytes**) cut back out of the new pages, both again hashed to
    #   the old digests — **0 bytes removed, `head` / `shell` / `chrome`
    #   unmoved**. A role WITHOUT `project.pnl` is pinned byte-for-byte against
    #   `3a14375` in `tests/test_pnl_access.py`. The old values:
    #       ("projects", "/projects/"): ("1dcdc0e2798636eb", 49548,
    #        {"head": "35ced4411e03de2e", "shell": "75cda0afbae27209",
    #         "chrome": "89e92c31f075ea28", "main": "b61a7f3ca9178c9b"})
    #       ("project page", …): ("74f683d1a779159f", 76963,
    #        {"head": "0565b7d2103f190b", "shell": "75cda0afbae27209",
    #         "chrome": "b03da1368479ad8b", "main": "85908eff05b3e868"})
    # ⚠ **RE-BASELINED 29 October 2026 — §0 fifty-eighth block, item 4.**
    #   `main` only: a **P&L** button per row. See the dashboard row above for
    #   the measurement that covers all three pages. The old value:
    #       ("projects", "/projects/"): ("8e8cf8516aaff984", 50009,
    #        {"head": "35ced4411e03de2e", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "f2fdcc9f984ceb87", "main": "e7babe8cdc1b11fc"})
    ("projects",        "/projects/"):                 ("5dc54424bd834b33", 53415,
        {"head": "9e31cc817dae337f", "shell": "a1e6c63a6d4c6ac2", "chrome": "684a3790917ca917", "main": "ad5823648d39b9cc"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3092 bytes
    # ⚠ **RE-BASELINED 28 October 2026 — `main` ONLY** (the Yogesh meeting's
    #   project-page bugs: documents raised from a BOQ now follow it onto its
    #   project, and only a chain's latest revision is totalled). `main` gains
    #   the *Raised from these BOQs* panel (**+2,200 bytes** on this world) and
    #   three panel captions change wording. Measured before the baseline was
    #   touched: with that panel cut out and the three captions put back, this
    #   page and all four non-`project.pnl` roles' pages in
    #   `tests/test_pnl_access.py` were BYTE-IDENTICAL to the old renders —
    #   **0 other bytes moved, `head` / `shell` / `chrome` unmoved**. The golden
    #   world has no superseded revision, so the BOQ total did not move here;
    #   `tests/test_project_rollup_oct28.py` covers that. The old value:
    #       ("project page", …): ("ed03e4a8109be779", 83331,
    #        {"head": "0565b7d2103f190b", "shell": "75cda0afbae27209",
    #         "chrome": "b03da1368479ad8b", "main": "ebeb42c9b7836fc1"})
    # ⚠ **RE-BASELINED 29 October 2026 — CLIENT_CHANGES.md §0's fifty-eighth
    #   block, item 2** (labour on the project automatically). `main` ONLY:
    #   the Site Labour panel gains a **per-worker rollup** table per group
    #   (`projectview._worker_rollup()`, every figure out of
    #   `attendance.worker_costs()`), a *"Every marking, day by day"* heading
    #   over the table that was already there, the **advances outstanding**
    #   information line and the **amber off-project** line. **+2,197 bytes.**
    #
    #   Measured before the baseline was touched, by reverting `projectview.py`,
    #   `attendance.py` and `payroll.py` and re-running this one test: `main`
    #   came back `56a6540cddadb9c8` **exactly**, and `head` / `shell` /
    #   `chrome` never moved at either end. The rollup's stylesheet travels
    #   INSIDE the panel (`projectview.ROLLUP_CSS`, `PNL_CSS`'s arrangement),
    #   so all four non-`attendance.view` roles in `tests/test_pnl_access.py`
    #   are still BYTE-IDENTICAL to `3a14375` and that file needed no
    #   re-baseline at all. The old value:
    #       ("project page", …): ("b40cbe634515dfca", 85531,
    #        {"head": "0565b7d2103f190b", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "b51ad113e721dcbe", "main": "56a6540cddadb9c8"})
    #
    # ⚠ **RE-BASELINED AGAIN, same day — §0's fifty-eighth block, item 3**
    #   (attach a loose document by hand). `main` ONLY, a second time:
    #   `main` gains the *Attach document* panel — two pickers and a
    #   paragraph, no figure of any kind (`projtag.picker_html()`).
    #   **+2,353 bytes.** Measured by reverting `projectview.py` and deleting
    #   `projtag.py`: `main` came back `80ecaec1f7e9225b` exactly and
    #   `head` / `shell` / `chrome` never moved. The panel is drawn only for a
    #   holder of `project.edit`, which is why only ONE of the eight rows in
    #   `tests/test_pnl_access.py` moved with it. The value before item 3:
    #       ("project page", …): ("743a34c2b98c0499", 87728,
    #        {"head": "0565b7d2103f190b", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "b51ad113e721dcbe", "main": "80ecaec1f7e9225b"})
    # ⚠ **RE-BASELINED 29 October 2026 — §0 fifty-eighth block, item 4**, the
    #   third time this row moves today. `main` only: *Planned margin against
    #   actual* with the coverage sentence, and the cost-tagged-to-no-project
    #   band. See the dashboard row above for the measurement. The value
    #   before item 4:
    #       ("project page", …): ("994d761e70c27a65", 90081,
    #        {"head": "0565b7d2103f190b", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "b51ad113e721dcbe", "main": "a2c311e0f0026245"})
    #
    #   ⚠ **CORRECTED, same pass: `main` is `eccbe9476dd92798`, not
    #     `96c7f5605c3519b0`.** The first value was measured while
    #     `pnl.po_coverage()` read `tip["boq_id"]` — but `tips_of()` returns
    #     the BOQ RECORDS, which carry `id` — so it silently reported **0 of
    #     0** and the golden world's panel printed *"no BOQ lines to say how
    #     much of this job has been bought"*. Writing
    #     `tests/test_pnl_oct28.py` found it. The 160-byte difference between
    #     the two is the real coverage sentence, which is what the item is
    #     for. The wrong value is recorded here rather than quietly dropped:
    #     a golden captured from a broken render is the one mistake this file
    #     cannot catch by itself.
    #
    #   ⚠ **AND CORRECTED ONCE MORE, 33 bytes smaller:
    #     `main` is `4966a1cb8a5c0421`.** This item had also reworded the Cash
    #     heading to *"received and still owed · GST included"*, which bought
    #     nothing and broke `tests/test_pnl.py::test_the_tax_exclusive_and_tax
    #     _inclusive_sections_never_mix`, a test that pins that heading
    #     verbatim for ABOUT.md §7 gap 31's reason. The reword was **reverted**
    #     rather than the test re-baselined: the heading is back to
    #     `<h3>Cash <span>GST included</span></h3>`, exactly as the
    #     forty-seventh block left it. That is the 33 bytes.
    # ⚠ **RE-BASELINED AGAIN, same day — §0 fifty-eighth block, item 5** (the
    #   pictures). `main` ONLY: the P&L panel gains the *Where the money went*
    #   heading, the **money waterfall** and the **progress spider** as inline
    #   SVG, each with its own plain-text table. **+10,576 bytes**, which is
    #   mostly the two tables and the SVG geometry.
    #
    #   `head` / `shell` / `chrome` unmoved, because the chart stylesheet
    #   travels INSIDE the panel (`pnl_chart.CHART_CSS`, `PNL_CSS`'s
    #   arrangement) — which is also why all eight rows of
    #   `tests/test_pnl_access.py` are untouched by this item: none of those
    #   four roles holds `project.pnl`. Measured by reverting `pnl.py`,
    #   `pnl_chart.py`, `projectview.py` and `dashboard.py`: every old value
    #   came back exactly. The value before item 5:
    #       ("project page", …): ("e296b70a116cbce6", 91222,
    #        {"head": "0565b7d2103f190b", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "b51ad113e721dcbe", "main": "4966a1cb8a5c0421"})
    # ⚠ **RE-BASELINED 31 October 2026 — `main` ONLY, +885 bytes**
    #   (CLIENT_CHANGES.md §0 sixty-third block): the RECEIPTS in *Raised from
    #   these BOQs* (C2); the coverage count beside *Spent to date* and *the
    #   running position, billed less spent* beside *Margin to date* (C5); the
    #   spider's six axes — BOQ and procurement in, *bought* out, its caption
    #   "five measures" now "six" (C7). No print route; no printed document
    #   moved. The old row:
    #       ("41138146f3c01040", 101785, {..., "main": "b619482943b36e59"})
    ("project page",    f"/projects/view/{GOLD_PROJECT}"): ("3ea2483e86bf9a24", 102670,
        {"head": "0565b7d2103f190b", "shell": "a1e6c63a6d4c6ac2", "chrome": "7ea32f8551745f31", "main": "78a814da4ebe21aa"}),   # §0 59th B1: moved=['chrome', 'main'], -13 bytes
    # ⚠ `employees` keeps the TABLE-FIT baseline of 30 October 2026 (a121953):
    #   the sixty-third block did not move this row, the table fit did
    #   (+3103 bytes, moved=['head', 'main']). Verified three-way against
    #   09a028b: of the 17 rows in this table 15 moved on the table-fit side
    #   and 2 (dashboard, project page) on the sixty-third-block side — NONE
    #   on both, so each row has exactly one live baseline.
    ("employees",       "/employee/"):                 ("d7508089bf4495e2", 69454,
        {"head": "2935842182bb629b", "shell": "a1e6c63a6d4c6ac2", "chrome": "5f85e9f89efcd51e", "main": "fffd120cf79d9096"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3103 bytes
    # ⚠ **RE-BASELINED 27 October 2026 — CLIENT_CHANGES.md §0's fifty-fourth
    #   block, item B** (the attendance search). The only golden this pass
    #   moves, and `head` and `main` only: `main` gains the **Search** button
    #   in the page-top, and `head` gains the eight lines of `.att-presets`
    #   CSS that the search page needs and that rides in the module's shared
    #   `ATTENDANCE_STYLES`.
    #
    #   Measured before the baseline was touched, by rendering this page with
    #   the change and again with the button and the CSS block stripped back
    #   out: **+506 bytes, 10 lines added, 0 removed**, and the stripped
    #   render reproduced the old digest exactly. `shell` and `chrome` did not
    #   move — no rail entry was added, which is why no OTHER page and no
    #   printed document moved at all. The old values:
    #       ("772b3d71abb8f8ee", 72731,
    #        {"head": "f7e83482d5632c42", "shell": "75cda0afbae27209",
    #         "chrome": "864f7a2ba55bb64a", "main": "bb8159e0b0291642"})
    # ⚠ **RE-BASELINED 29 October 2026 — `main` ONLY** (CLIENT_CHANGES.md §0
    #   fifty-fifth block, the payslip). The muster gained one link, Payslips,
    #   between Search and Employees: **+61 bytes, exactly that one line**, and
    #   `head`, `shell` and `chrome` did not move — no rail entry, so no other
    #   page and no printed document moved. The old values:
    #       ("aaa704c1ef16122e", 73237,
    #        {"head": "8fb0c3cb6ad47c05", "shell": "75cda0afbae27209",
    #         "chrome": "864f7a2ba55bb64a", "main": "4fd344e6ce33374a"})
    ("attendance",      f"/attendance/?date={GOLD_DATE}"): ("fb37e3de3ebd00c1", 73290,
        {"head": "8fb0c3cb6ad47c05", "shell": "a1e6c63a6d4c6ac2", "chrome": "5840edff333df8f9", "main": "99e031f5f5f6af8e"}),   # §0 59th B1: moved=['chrome'], -8 bytes
    ("charges",         "/charge/"):                   ("20faf5129217e51b", 69218,
        {"head": "8d18d2cb4f314105", "shell": "a1e6c63a6d4c6ac2", "chrome": "ecd8e5237db40965", "main": "0117146916a6da27"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3225 bytes
    ("address book",    "/address/"):                  ("334040ac7348c58e", 75642,
        {"head": "0a1c0d68158bc7e5", "shell": "a1e6c63a6d4c6ac2", "chrome": "595eb9470c1c25e1", "main": "7e67e775827dc7af"}),   # §0 59th B1: moved=['chrome'], -8 bytes
    # ⚠ **RE-BASELINED 25 September 2026 — `main` ONLY, and it is the ONE
    #   golden this application's go-live hardening was always going to move.**
    #   ABOUT.md §7 gap 36 is closed by adding a **Starting Numbers** section to
    #   this form, so the page that owns every series control gains nine boxes.
    #   A gap that can only be closed by putting a control on a page cannot be
    #   closed without moving that page's digest.
    #
    #   Measured before the baseline was touched, by rendering the page twice
    #   from the same process — once as it stands, once with the new section's
    #   HTML removed:
    #
    #       +5,560 bytes · 27 lines ADDED · **0 lines REMOVED**
    #
    #   **Purely additive.** Every line of the identity, bank, draft-PO,
    #   challan, labour, charge-head and measurement-column sections is
    #   byte-identical, `head` / `shell` / `chrome` did not move, and **no
    #   print golden moved at all** — the nine printed documents are untouched,
    #   which is what the minters' scan-move to `series.py` had to prove and
    #   did.
    #
    #   The old values, kept rather than overwritten in silence:
    #       ("f12eaac1c07efbaa", 74589,
    #        {"head": "ce8721ccb87d2120", "shell": "75cda0afbae27209",
    #         "chrome": "d107029c10eb2dec", "main": "741824ea93f3b3cb"})
    #
    # ⚠ **RE-BASELINED 21 October 2026 — `main` ONLY, −4 bytes.** The tagline
    #   default became the client's own wording (CLIENT_CHANGES.md §0, the
    #   fiftieth block): "Fire Protection Systems & Services" →
    #   "Fire Protection and Safety Engineers". The Tagline box prints it twice
    #   — as its value, since the pinned identity sets no tagline, and as the
    #   example in its placeholder — and each is two bytes shorter, the old
    #   one's `&` having printed as `&amp;`. Was
    #       ("a499293306ea5d30", 80230, {..., "main": "8cbae4b20e7083ef"})
    # ⚠ **RE-BASELINED AGAIN 5 October 2026 — `main` ONLY**, for the Work
    #   Order Series section (CLIENT_CHANGES.md §0 forty-first block, ruling F:
    #   "own prefix + next number in /settings"). A control that has to be ON
    #   this page cannot be added without moving this page's digest.
    #
    #   Measured before the baseline was touched: with the new section cut out
    #   of the rendered page, it hashed to the 25 September digest below
    #   exactly — **+1,343 bytes · 30 lines ADDED · 0 REMOVED**. Every other
    #   section is byte-identical, `head` / `shell` / `chrome` did not move, and
    #   no print golden moved. The values it replaces:
    #       ("a499293306ea5d30", 80230,
    #        {"head": "ce8721ccb87d2120", "shell": "75cda0afbae27209",
    #         "chrome": "d107029c10eb2dec", "main": "8cbae4b20e7083ef"})
    # ⚠ **RE-BASELINED 5 October 2026 — `main` ONLY**, for the work order's
    #   Default Terms & Conditions box in the Work Order Series section
    #   (CLIENT_CHANGES.md §0 forty-third block, R7: "default_terms in the
    #   WO's own settings record, editable at /settings").
    #
    #   Measured before the baseline was touched: with the new box cut out
    #   of the rendered page, it hashed to the digest below exactly —
    #   **+483 bytes · 6 lines ADDED · 0 REMOVED**. `head` / `shell` /
    #   `chrome` did not move. The values it replaces:
    #       ("5b4a57215d0e88c9", 81573,
    #        {"head": "ce8721ccb87d2120", "shell": "75cda0afbae27209",
    #         "chrome": "d107029c10eb2dec", "main": "87037b9058f6019f"})
    # ⚠ **RE-BASELINED 23 October 2026, at the merge of the office and laptop
    #   lines — `main` ONLY, −4 bytes**: the notes above, combined. The office
    #   line's Work Order Series section and Default Terms box are here (+1,343,
    #   +483) and so is the laptop line's tagline default (−4). Was
    #       ("ba78271ef9858935", 82056, {..., "main": "eb2f1c0f23b401d0"})
    # ⚠ **RE-BASELINED 26 October 2026 — `main` ONLY, +2,959 bytes**, for the
    #   Owner-only *Signature & Stamp* section (CLIENT_CHANGES.md §0, the
    #   fifty-third block, change 1). This page is rendered for an OWNER, who
    #   is shown the control; a Director is not, and sees the old bytes.
    #
    #   Measured before the baseline was touched: with the new section cut out
    #   of the rendered page it is 82,052 bytes and `main` hashes to
    #   `56df0925a4c75aa4` — the digest below — exactly. `head` / `shell` /
    #   `chrome` did not move; the section is styled on its elements so
    #   `SETTINGS_STYLES` is untouched. The values it replaces:
    #       ("6fb1e35f5488db36", 82052,
    #        {"head": "ce8721ccb87d2120", "shell": "75cda0afbae27209",
    #         "chrome": "d107029c10eb2dec", "main": "56df0925a4c75aa4"})
    # ⚠ **RE-BASELINED AGAIN 29 October 2026 — `main` ONLY, +1,523 bytes** —
    #   the **Units of Measure** section (CLIENT_CHANGES.md §0 **fifty-ninth**
    #   block, B3): the seven built-in units named in the hint, the custom-unit
    #   textarea and its `name|UQC` explanation. `head`, `shell` and `chrome`
    #   are byte-identical, so no stylesheet and no shell byte moved — the
    #   section is markup and nothing else. **It is the only page this item
    #   moves**: every other form that gained the dropdown is unpinned.
    #   The value before B3:
    #       ("settings", "/settings/"): ("f8f0d0cb199640ad", 85018,
    #        {"head": "ce8721ccb87d2120", "shell": "a1e6c63a6d4c6ac2",
    #         "chrome": "932b769fd94b56af", "main": "96a34b1da10ef362"})
    ("settings",        "/settings/"):                 ("510db93db42692db", 86541,
        {"head": "ce8721ccb87d2120", "shell": "a1e6c63a6d4c6ac2", "chrome": "932b769fd94b56af", "main": "dcd932dfd8ac277d"}),   # §0 59th B3: moved=['main'], +1523 bytes
    # ⚠ re-baselined 22 September 2026 — `head` ONLY, by the four CSS rules the
    # role picker and the empty action cell needed (`AUTH_ADMIN_STYLES`, +262
    # bytes). `main` is byte-identical and that is the measurement that matters
    # here: this page is hashed as an OWNER, who may administer every account
    # and reach `/roles`, so every link the pass made conditional is still
    # drawn. A moved `main` would have meant the Owner lost something.
    # ⚠ re-baselined 29 October 2026 — `main` ONLY (CLIENT_CHANGES.md §0
    # fifty-sixth block): the Staff access button beside Roles, **+58 bytes,
    # exactly that one line**. The old values:
    #     ("6f28cf4801fb6f4c", 65758, {..., "main": "645012baa0685fdd"})
    ("users",           "/users"):                     ("1078087dbad64d66", 68911,
        {"head": "b4056a0765053dfb", "shell": "a1e6c63a6d4c6ac2", "chrome": "f7619f738bb44694", "main": "8b729748e54dd904"}),   # table fit 30 Oct 2026: moved=['head', 'main'], +3103 bytes
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
    The shape the split relies on: every page here carries the shell's
    stylesheet, a `<nav` and a `<main`, in that order, after its `<head>`. A
    page that lost any of them has lost the chrome this file exists to measure.
    """
    for (name, url) in PAGES:
        html = client.get(url).get_data(as_text=True)
        cuts = [html.find(m) for _n, m in PAGE_BLOCKS]
        assert all(c >= 0 for c in cuts), f"{name}: a marker is missing ({cuts})"
        assert cuts == sorted(cuts), f"{name}: the markers are out of order"


def test_the_head_element_carries_none_of_the_shell(client, world):
    """
    ⚠ **What "the sidebar moved only the chrome" rests on.** The shell's
    stylesheet and script are emitted by `_nav()` in the BODY, so a page's
    `<head>` element is exactly what it was before the redesign — its own
    `<title>`, the favicon, and the style constants it always loaded. That is
    asserted two ways: nothing of the shell is inside `<head>…</head>`, and
    nothing but whitespace and the `<body>` opening sits between `</head>` and
    the shell's first byte. `chrome.BASE_STYLES` being byte-identical to the
    extraction commit's (`efa3467`) is the third leg, and it was measured in
    the sidebar commit rather than assumed.
    """
    import re

    import chrome

    shell_start = chrome.CHROME_STYLES.strip()
    for (name, url) in PAGES:
        html = client.get(url).get_data(as_text=True)
        head = html[html.index("<head>"):html.index("</head>")]
        for token in ("nav.rail", "railToggle", ".topbar", "--rail-w"):
            assert token not in head, f"{name}: {token!r} leaked into <head>"
        between = html[html.index("</head>") + len("</head>"):html.index(shell_start)]
        assert re.fullmatch(r"\s*<body[^>]*>\s*", between), (
            f"{name}: something other than <body> sits between </head> and the "
            f"shell: {between!r}")
