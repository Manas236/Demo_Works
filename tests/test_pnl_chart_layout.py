"""
THE PROJECT PAGE'S CHARTS DO NOT OVERLAP — measured in a real browser.

CLIENT_CHANGES.md §0's **sixty-ninth** block, item 3 (6 November 2026). The
other chart tests read the HTML; this one LAYS IT OUT. `/projects/view` is
rendered for several worlds, each loaded into headless Chromium at **360,
390, 768 and 1280 px**, and every piece of text inside `.pnl-figs` — SVG
`<text>` and HTML text nodes alike — is measured with the browser's own
`getBoundingClientRect()` / `Range.getClientRects()`. The test fails on:

* any two text boxes that intersect (more than a 0.5 px sliver);
* any SVG text that runs outside its own `<svg>` (it would be clipped);
* anything in the chart region reaching past the right edge of the window
  (the page's other panels are wider than a phone on their own, and that
  predates this file).

The worlds: an **RIL Jamnagar-like** job (purchase orders, a non-taxable PO
charge, a nil work-order head, charges, site labour, a BOQ well above what is
billed), a job with **all five cost heads non-zero**, a job whose **two plan
rules sit close together** (the *BOQ value* / *planned margin* label clash),
one with a **sliver** of a slice, and one with **no cost at all**.

⚠ **Skipped, not failed, where there is no browser.** The production box has
  no Chromium and needs none; Playwright is a development tool here exactly
  as `assets/build_banner.py`'s dependencies are. Set `PNL_SHOT_DIR` to also
  write a screenshot of the charts per world and width.
"""

import os
import pathlib

import pytest

from store import STORE
import employee as EMP

_OWNED = ("projects", "boqs", "purchases", "ra_bills", "invoices", "proformas",
          "work_orders", "charges", "attendance", "receipts", "employees",
          "delivery_challans", "measurements", "payslips", "pay_entries",
          "addresses", "purchase_orders")

PID = "lay-p1"
SITE = "lay-site"
WIDTHS = (360, 390, 768, 1280)


@pytest.fixture(scope="module")
def browser():
    pw_mod = pytest.importorskip("playwright.sync_api")
    try:
        pw = pw_mod.sync_playwright().start()
    except Exception as e:                         # pragma: no cover
        pytest.skip(f"playwright will not start: {e}")
    b, why = None, ""
    # Playwright's own browser first; then a Chromium named by PNL_CHROMIUM,
    # or a shared install (a Python Playwright newer than the browsers on the
    # box will not find them by itself).
    for exe in (None, os.environ.get("PNL_CHROMIUM"), "/opt/pw-browsers/chromium"):
        if exe is not None and not os.path.exists(exe):
            continue
        try:
            b = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
            break
        except Exception as e:                     # pragma: no cover
            why = str(e).splitlines()[0]
    if b is None:                                  # pragma: no cover
        pw.stop()
        pytest.skip(f"no Chromium to lay the page out in: {why}")
    yield b
    b.close()
    pw.stop()


@pytest.fixture()
def world(client):
    saved = {k: dict(STORE.setdefault(k, {})) for k in _OWNED}
    for k in _OWNED:
        STORE[k].clear()
    STORE["addresses"][SITE] = {"id": SITE, "label": "Jamnagar Refinery",
                                "type": "site", "archived": False}
    STORE["projects"][PID] = {
        "id": PID, "name": "RIL Jamnagar", "norm_name": "ril jamnagar",
        "client": "Reliance Industries Ltd", "notes": "",
        "site_address_id": SITE, "site_address": "Jamnagar Refinery",
        "created_at": "2026-08-01 09:00", "updated_at": "2026-08-01 09:00"}
    yield client
    for k, was in saved.items():
        STORE[k].clear()
        STORE[k].update(was)


# ── the records ─────────────────────────────────────────────────────────────

def _boq(qty, sup, sup_base, ins, ins_base, n_lines=1):
    lines = []
    for i in range(n_lines):
        lines.append({
            "line_id": f"{i:012d}", "item_no": str(i + 1), "is_header": False,
            "description": "MS ERW pipe", "unit": "Mtrs", "total_qty": str(qty),
            "supply_rate": str(sup), "supply_base_rate": str(sup_base),
            "supply_escalation_pct": "0", "supply_discount_pct": "",
            "install_rate": str(ins), "install_base_rate": str(ins_base),
            "install_escalation_pct": "0", "install_discount_pct": ""})
    STORE["boqs"]["lay-b1"] = {
        "id": "lay-b1", "ref": "SF/BOQ/26-27/0031", "rev_no": 0,
        "supersedes": "", "date": "2026-08-02", "project_id": PID,
        "line_items": lines, "subtotal": 0.0}


def _ra(claim):
    STORE["ra_bills"]["lay-r1"] = {
        "id": "lay-r1", "ref": "SF/RA/26-27/0004", "ra_no": 1,
        "date": "2026-10-15", "boq_id": "lay-b1", "leg": "supply",
        "status": "issued", "claim_subtotal": claim,
        "grand_total": round(claim * 1.18, 2), "claims": [],
        "tax_invoice_ref": "", "deduction_total": 0.0, "net_payable": claim,
        "tax_amount": round(claim * 0.18, 2)}


def _po(taxable, exempt=0.0):
    charges = ([{"label": "Freight", "amount": exempt, "taxable": False}]
               if exempt else [])
    STORE["purchases"]["lay-po1"] = {
        "id": "lay-po1", "ref": "SF/PO/26-27/0012", "date": "2026-09-12",
        "status": "Issued", "vendor_name": "Jindal Pipes", "project_id": PID,
        "boq_id": "", "taxable_value": taxable, "subtotal": taxable,
        "grand_total": round(taxable * 1.18 + exempt, 2), "charges": charges,
        "items": [{"line_id": "000000000000", "qty": 10, "rate": 60}]}


def _wo(amount):
    STORE["work_orders"]["lay-wo1"] = {
        "id": "lay-wo1", "ref": "SF/WO/26-27/0003", "project_id": PID,
        "status": "issued", "tracks": "both", "gst_rate": 18.0,
        "contractor_name": "K. Patil", "lines": [
            {"line_id": "aaaaaaaaaaa1", "description": "Pipe laying",
             "unit": "Mtrs", "qty": 1.0, "material_rate": 0.0,
             "labour_rate": amount}]}


def _charge(amount):
    STORE["charges"]["lay-c1"] = {
        "id": "lay-c1", "date": "2026-09-20", "person": "R. Kadam",
        "head": "Travel", "description": "Site visit", "project_id": PID,
        "taxable_amount": amount, "gst_amount": 0.0,
        "created_at": "2026-09-20 10:00"}


def _labour(days, rate):
    STORE["employees"]["lay-e1"] = {
        "id": "lay-e1", "name": "Ramesh Patil", "code": "W-01",
        "designation": "Fitter", "day_rate": rate, "active": True}
    for d in range(days):
        mid = f"lay-m{d}"
        STORE["attendance"][mid] = {
            "id": mid, "employee_id": "lay-e1", "employee_name": "Ramesh Patil",
            "employee_code": "W-01",
            "date": f"2026-{9 + d // 28:02d}-{d % 28 + 1:02d}",
            "status": "present", "ot_hours": 0.0, "day_rate": rate,
            "site": "Jamnagar Refinery", EMP.SITE_ADDRESS_FIELD: SITE,
            EMP.SITE_SOURCE_FIELD: EMP.SITE_BOOK, "project_id": PID,
            "project_name": "RIL Jamnagar"}


def _jamnagar():
    """Billed well short of the BOQ; POs, a non-taxable freight charge, NO
    work order (a nil head), travel charges, a month of site labour."""
    _boq(qty=1000, sup=5000, sup_base=3500, ins=3500, ins_base=2500)
    _ra(3240000.0)
    _po(2160000.0, exempt=12500.0)
    _charge(85000.0)
    _labour(days=40, rate=900.0)


def _all_five():
    _boq(qty=400, sup=6000, sup_base=4200, ins=3000, ins_base=2000)
    _ra(2600000.0)
    _po(1250000.0, exempt=180000.0)
    _wo(420000.0)
    _charge(260000.0)
    _labour(days=50, rate=1100.0)


def _close_refs():
    """Planned revenue 12L and planned margin 10.5L — two dashed rules a few
    pixels apart, which is what put one label on top of the other."""
    _boq(qty=100, sup=10000, sup_base=1000, ins=2000, ins_base=500)
    _ra(1100000.0)
    _po(60000.0)
    _charge(15000.0)


def _sliver():
    """One head a fraction of a percent of the total: a slice too thin to
    carry its own label, so it goes to the legend."""
    _boq(qty=1000, sup=5000, sup_base=3500, ins=3500, ins_base=2500)
    _ra(3000000.0)
    _po(2500000.0, exempt=900.0)
    _wo(300000.0)
    _charge(1200.0)
    _labour(days=6, rate=800.0)


def _nothing():
    _boq(qty=100, sup=1000, sup_base=700, ins=500, ins_base=300)


WORLDS = {"jamnagar": _jamnagar, "all-five": _all_five,
          "close-refs": _close_refs, "sliver": _sliver, "no-cost": _nothing}


# ── the measurement ─────────────────────────────────────────────────────────

_MEASURE = r"""
() => {
  const root = document.querySelector('.pnl-figs');
  if (!root) return {missing: true};
  const boxes = [];
  const vis = el => {
    for (let e = el; e && e !== document; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden') return false;
    }
    return true;
  };
  // SVG text: one box per <text>, which covers its own tspans.
  for (const t of root.querySelectorAll('svg text')) {
    if (!vis(t) || !t.textContent.trim()) continue;
    const r = t.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) continue;
    const svg = t.ownerSVGElement.getBoundingClientRect();
    boxes.push({txt: t.textContent.trim(), x: r.left, y: r.top, w: r.width,
                h: r.height, svg: true,
                out: r.left < svg.left - 0.5 || r.right > svg.right + 0.5 ||
                     r.top < svg.top - 0.5 || r.bottom > svg.bottom + 0.5});
  }
  // HTML text: one box per laid-out line of each text node.
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    if (!n.textContent.trim()) continue;
    const p = n.parentElement;
    if (p.closest('svg') || !vis(p)) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      if (r.width < 0.5 || r.height < 0.5) continue;
      boxes.push({txt: n.textContent.trim().slice(0, 40), x: r.left, y: r.top,
                  w: r.width, h: r.height, svg: false, out: false});
    }
  }
  const hits = [];
  const eps = 0.5;
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const ix = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const iy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ix > eps && iy > eps) hits.push([a.txt, b.txt]);
    }
  }
  return {
    count: boxes.length,
    hits: hits,
    clipped: boxes.filter(b => b.out).map(b => b.txt),
    // ⚠ The CHART REGION's overflow, not the page's: other panels on this
    //   page (the BOQ and purchase tables) are wider than a phone and scroll
    //   on their own, which is not this file's business and predates it.
    overflow: Math.max(0, ...[root, ...root.querySelectorAll('*')].map(
      e => e.getBoundingClientRect().right)) - window.innerWidth,
  };
}
"""


def measure(browser, html, width, shot=None):
    page = browser.new_page(viewport={"width": width, "height": 900},
                            device_scale_factor=2 if shot else 1)
    try:
        # Nothing on this page may reach the network; every request is refused
        # so a stray CDN reference would show up as a broken render here.
        page.route("**/*", lambda route: route.abort())
        page.set_content(html, wait_until="domcontentloaded")
        got = page.evaluate(_MEASURE)
        if shot:
            # The app shell's top bar is sticky and would be photographed
            # over the charts; it is unstuck for the picture only, after the
            # measurement above.
            page.add_style_tag(content=".topstack{position:static!important}")
            el = page.query_selector(".pnl-figs")
            if el:
                el.screenshot(path=str(shot))
        return got
    finally:
        page.close()


@pytest.mark.parametrize("name", sorted(WORLDS))
def test_no_chart_text_overlaps_at_any_width(world, browser, name):
    WORLDS[name]()
    html = world.get(f"/projects/view/{PID}").get_data(as_text=True)
    shots = os.environ.get("PNL_SHOT_DIR")
    problems = []
    for width in WIDTHS:
        shot = (pathlib.Path(shots) / f"{name}-{width}.png") if shots else None
        if shot:
            shot.parent.mkdir(parents=True, exist_ok=True)
        got = measure(browser, html, width, shot)
        assert not got.get("missing"), "the charts were not on the page"
        assert got["count"] > 10, f"measured almost nothing at {width}px: {got}"
        if got["hits"]:
            problems.append(f"{width}px overlaps: {got['hits']}")
        if got["clipped"]:
            problems.append(f"{width}px text outside its svg: {got['clipped']}")
        if got["overflow"] > 0:
            problems.append(f"{width}px charts overflow by {got['overflow']:.0f}px")
    assert not problems, f"{name}: " + "; ".join(problems)
